"""Security behavior tests against a disposable database, never the application DB."""
import json
import logging
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, BoundedSemaphore, Event, Lock
from urllib.parse import parse_qs, urlparse

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from database import Base, get_db
from models import AuditLog, Group, GroupMember, Room, RoomAssignment, User
from pilot import accounts, config, delivery, security
from pilot.domain_models import DomainAudit
from pilot.security_models import (
    AccountSession,
    Enrollment,
    OutboxEvent,
    RateBucket,
    SecurityToken,
    SupportCase,
)

PASSWORD = "Correct-Horse-Pilot-123!"


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.getenv("SECURITY_TEST_DATABASE_URL") else []))
def security_site(tmp_path, monkeypatch, request):
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    schema = None
    if request.param == "postgresql":
        url = os.environ["SECURITY_TEST_DATABASE_URL"]
        if "test" not in url.rsplit("/", 1)[-1].split("?", 1)[0]:
            raise RuntimeError("Security tests require an explicitly named test database")
        schema = "security_test_" + secrets.token_hex(8)
        bootstrap = create_engine(url)
        with bootstrap.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        engine.rate_limit_bind = create_engine(url, connect_args={"options": f"-csearch_path={schema}"},
                                              pool_size=2, max_overflow=2)
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'security-only.sqlite3'}", connect_args={"check_same_thread": False})
        engine.rate_limit_bind = create_engine(engine.url, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(security, "password_hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))
    app = FastAPI()
    app.include_router(security.router)
    app.include_router(accounts.router)

    def test_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    with factory() as db:
        for name, role in (("student", "user"), ("second", "user"), ("admin", "admin")):
            user = User(email=f"{name}@example.org", name=name, class_name="Engineering", student_id=name,
                        gender="other", role=role, email_verified=True, is_active=True,
                        password_hash=security.hash_password(PASSWORD))
            db.add(user)
        db.commit()
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()
    engine.rate_limit_bind.dispose()
    if schema:
        with bootstrap.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        bootstrap.dispose()


def csrf(client):
    value = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": value}


def login(client, identity="student"):
    result = client.post("/auth/login", json={"email": f"{identity}@example.org", "password": PASSWORD}, headers=csrf(client))
    assert result.status_code == 200, result.text
    return result


def raw_mail_token(factory, purpose):
    with factory() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.purpose == purpose).order_by(OutboxEvent.id.desc()))
        payload = delivery.decrypt_payload(event)
        link = payload["body"].splitlines()[-1]
        return parse_qs(urlparse(link).fragment.split("?", 1)[1])["token"][0], event.id


def password_registration_payload(**changes):
    return {"email": "new-password@example.org", "student_id": " ۱۲۳۴۵۶ ", "name": "دانشجوی آزمایشی",
            "class_name": "مهندسی", "gender": "male", "password": PASSWORD, **changes}


def test_password_registration_needs_no_roster_or_email_and_can_login(security_site, monkeypatch):
    client, factory = security_site
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    payload = password_registration_payload(name="  دانشجوی آزمایشی  ", class_name=" مهندسی ")
    assert client.post("/auth/register", json=payload).status_code == 403
    result = client.post("/auth/register", json=payload, headers=csrf(client))
    assert result.status_code == 201, result.text
    assert result.json()["student_id"] == "123456"
    assert result.json()["name"] == "دانشجوی آزمایشی"
    assert result.json()["class_name"] == "مهندسی"
    assert result.json()["email_verified"] is False
    assert result.json()["eligibility"] == {"status": "eligible", "pool": "male", "cycle": config.ACTIVE_CYCLE}
    assert client.get("/auth/me").json()["id"] == result.json()["id"]
    with factory() as db:
        user = db.get(User, result.json()["id"])
        assert user.role == "user" and user.password_hash.startswith("$argon2id$")
        assert not user.email_verified and not user.notification_email
        assert db.scalar(select(OutboxEvent.id)) is None
        assert db.scalar(select(SecurityToken.id)) is None
    assert client.post("/auth/logout", headers=csrf(client)).status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": payload["email"], "password": "wrong"}, headers=csrf(client)).status_code == 401
    assert client.post("/auth/login", json={"email": payload["email"], "password": PASSWORD}, headers=csrf(client)).status_code == 200


@pytest.mark.parametrize("conflict", [{"email": "student@example.org"}, {"student_id": "student"}])
def test_password_registration_does_not_replace_existing_accounts(security_site, monkeypatch, conflict):
    client, factory = security_site
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    result = client.post("/auth/register", json=password_registration_payload(**conflict), headers=csrf(client))
    assert result.status_code == 409
    login(client)
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 3
        assert db.scalar(select(Enrollment.id)) is None


@pytest.mark.parametrize("change", [
    {"role": "admin"}, {"password": "short"}, {"gender": "other"},
    {"name": " a "}, {"student_id": " ۱ "}, {"class_name": "   "}, {"name": None},
])
def test_password_registration_validates_credentials_and_pool(security_site, monkeypatch, change):
    client, factory = security_site
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    assert client.post("/auth/register", json=password_registration_payload(**change), headers=csrf(client)).status_code == 422
    with factory() as db:
        assert len(list(db.scalars(select(User)))) == 3


@pytest.mark.parametrize("password", ["old-pass", "existing-password-" * 9])
def test_login_preserves_existing_credential_lengths(security_site, password):
    client, factory = security_site
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.org"))
        user.password_hash = security.hash_password(password)
        db.commit()
    result = client.post("/auth/login", json={"email": "student@example.org", "password": password}, headers=csrf(client))
    assert result.status_code == 200
    assert client.get("/auth/me").json()["id"] == result.json()["id"]


def test_disabled_email_auth_rejects_links_and_cancels_queued_mail(security_site, monkeypatch):
    client, factory = security_site
    assert client.post("/auth/forgot-password", json={"email": "student@example.org"}, headers=csrf(client)).status_code == 202
    raw, event_id = raw_mail_token(factory, "reset_password")
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    for path, body in [
        ("/auth/forgot-password", {"email": "student@example.org"}),
        ("/auth/reset-password", {"token": raw, "password": PASSWORD}),
        ("/auth/activate", {"token": raw, "password": PASSWORD}),
        ("/auth/verify-email", {"token": raw}),
        ("/auth/resend-verification", {"student_id": "student"}),
    ]:
        assert client.post(path, json=body, headers=csrf(client)).status_code == 404
    sent = []
    delivery.claim_events("disabled-email-test", session_factory=factory)
    assert delivery.deliver_one(event_id, "disabled-email-test", session_factory=factory, sender=sent.append) == "cancelled"
    assert sent == []
    with factory() as db:
        assert db.get(OutboxEvent, event_id).encrypted_payload is None
    login(client)


def test_password_registration_respects_existing_roster_restrictions(security_site, monkeypatch):
    client, factory = security_site
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    with factory() as db:
        db.add(Enrollment(student_id="123456", email="new-password@example.org", name="Approved Name", class_name="CS",
                          gender="male", pool="male", cycle=config.ACTIVE_CYCLE, status="ineligible"))
        db.commit()
    assert client.post("/auth/register", json=password_registration_payload(), headers=csrf(client)).status_code == 409
    with factory() as db:
        record = db.scalar(select(Enrollment).where(Enrollment.student_id == "123456"))
        assert record.user_id is None and record.name == "Approved Name"


def test_password_registration_keeps_email_correction_without_mail(security_site, monkeypatch):
    client, factory = security_site
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    result = client.post("/auth/register", json=password_registration_payload(), headers=csrf(client))
    assert result.status_code == 201
    with factory() as db:
        record_id = db.scalar(select(Enrollment.id).where(Enrollment.user_id == result.json()["id"]))
    login(client, "admin")
    response = client.patch(f"/admin/enrollments/{record_id}", json={"field": "email", "value": "changed@example.org",
                            "reason": "Operator reviewed email correction", "dry_run": False}, headers=csrf(client))
    assert response.status_code == 200, response.text
    assert response.json()["impact"]["email_verification_required"] is False
    assert client.post("/auth/login", json={"email": "changed@example.org", "password": PASSWORD}, headers=csrf(client)).status_code == 200
    with factory() as db:
        assert db.scalar(select(OutboxEvent.id)) is None
        assert db.get(Enrollment, record_id).email == "changed@example.org"


def test_csrf_required_and_legacy_tokens_rejected(security_site):
    client, _ = security_site
    assert client.post("/auth/login", json={"email": "student@example.org", "password": PASSWORD}).status_code == 403
    import jwt
    token = jwt.encode({"sub": "1", "type": "access", "exp": security.now() + timedelta(minutes=5)}, config.SECRET_KEY, algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_copied_access_token_revoked_on_logout(security_site):
    client, _ = security_site
    login(client)
    copied = client.cookies.get("access_token")
    assert client.post("/auth/logout", headers=csrf(client)).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {copied}"}).status_code == 401


def test_refresh_rotation_replay_closes_the_rotated_branch(security_site):
    client, factory = security_site
    login(client)
    original_refresh = client.cookies.get("refresh_token")
    with factory() as db:
        original_expiry = db.scalar(select(AccountSession.expires_at))
    assert client.post("/auth/refresh", headers=csrf(client)).status_code == 200
    access = client.cookies.get("access_token")
    with factory() as db:
        assert db.scalar(select(AccountSession.expires_at)) == original_expiry
    client.cookies.clear()
    client.cookies.set("refresh_token", original_refresh)
    assert client.post("/auth/refresh", headers=csrf(client)).status_code == 401
    client.cookies.clear()
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401


def test_reset_revokes_all_sessions_and_is_single_use(security_site):
    client, factory = security_site
    login(client)
    copied = client.cookies.get("access_token")
    assert client.post("/auth/forgot-password", json={"email": "student@example.org"}, headers=csrf(client)).status_code == 202
    raw, _ = raw_mail_token(factory, "reset_password")
    result = client.post("/auth/reset-password", json={"token": raw, "password": "Brand-New-Pilot-Password!"}, headers=csrf(client))
    assert result.status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {copied}"}).status_code == 401
    assert client.post("/auth/reset-password", json={"token": raw, "password": PASSWORD}, headers=csrf(client)).status_code == 400
    assert client.post("/auth/login", json={"email": "student@example.org", "password": PASSWORD}, headers=csrf(client)).status_code == 401


def test_owner_cannot_revoke_another_users_session_and_role_is_current(security_site):
    client, factory = security_site
    login(client, "second")
    with factory() as db:
        others_sid = db.scalar(select(AccountSession.sid))
    login(client)
    assert client.delete(f"/auth/sessions/{others_sid}", headers=csrf(client)).status_code == 404
    login(client, "admin")
    assert client.get("/admin/roster").status_code == 200
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        user.role = "user"
        db.commit()
    assert client.get("/admin/roster").status_code == 403


def test_claim_has_no_initiator_password_and_cannot_redirect_roster_email(security_site):
    client, factory = security_site
    with factory() as db:
        db.add(Enrollment(student_id="12345", email="approved@example.org", name="Student Name", class_name="Math",
                          gender="female", pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE))
        db.commit()
    wrong = client.post("/auth/register", json={"student_id": "12345", "email": "attacker@example.org"}, headers=csrf(client))
    unknown = client.post("/auth/register", json={"student_id": "98765", "email": "attacker@example.org"}, headers=csrf(client))
    assert wrong.status_code == unknown.status_code == 202
    assert wrong.json() == unknown.json()
    with factory() as db:
        assert not db.scalar(select(OutboxEvent))
        db.query(RateBucket).delete()
        db.commit()
    assert client.post("/auth/register", json={"student_id": "12345", "password": PASSWORD}, headers=csrf(client)).status_code == 422
    assert client.post("/auth/register", json={"student_id": "12345"}, headers=csrf(client)).status_code == 202
    raw, _ = raw_mail_token(factory, "claim")
    with factory() as db:
        assert not db.scalar(select(User).where(User.student_id == "12345"))
    result = client.post("/auth/activate", json={"token": raw, "password": PASSWORD}, headers=csrf(client))
    assert result.status_code == 200, result.text
    assert result.json()["email"] == "approved@example.org"
    assert not result.json()["discovery_consent"]
    assert client.post("/auth/activate", json={"token": raw, "password": PASSWORD}, headers=csrf(client)).status_code == 400


def test_roster_preview_never_silently_overwrites(security_site):
    client, factory = security_site
    login(client, "admin")
    row = {"student_id": "111", "email": "pilot@example.org", "name": "Pilot User", "class_name": "Math",
           "gender": "female", "pool": config.ALLOWED_POOLS[0], "cycle": config.ACTIVE_CYCLE}
    result = client.post("/admin/roster/import", json={"rows": [row, row], "dry_run": False, "reason": "Authorized pilot roster"}, headers=csrf(client))
    assert not result.json()["valid"]
    with factory() as db:
        assert not db.scalar(select(Enrollment))
    assert client.post("/admin/roster/import", json={"rows": [row], "dry_run": False, "reason": "Authorized pilot roster"}, headers=csrf(client)).json()["imported"] == 1
    result = client.post("/admin/roster/import", json={"rows": [row], "dry_run": False, "reason": "Authorized pilot roster"}, headers=csrf(client))
    assert result.json()["imported"] == 0


def test_limiter_survives_business_rollback_and_unrelated_login(security_site, monkeypatch):
    client, factory = security_site
    monkeypatch.setattr(config, "LOGIN_ACCOUNT_LIMIT", 2)
    for _ in range(2):
        assert client.post("/auth/login", json={"email": "student@example.org", "password": "wrong"}, headers=csrf(client)).status_code == 401
    login(client, "second")
    blocked = client.post("/auth/login", json={"email": "student@example.org", "password": PASSWORD}, headers=csrf(client))
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    with factory() as db:
        security.throttle(db, "test-charge", "same", 1, 3600)
        db.rollback()
        with pytest.raises(Exception) as raised:
            security.throttle(db, "test-charge", "same", 1, 3600)
        assert raised.value.status_code == 429


def test_atomic_limiter_allows_exactly_the_configured_concurrent_budget(security_site):
    _, factory = security_site

    def attempt(_):
        with factory() as db:
            try:
                security.throttle(db, "concurrent-test", "same", 4, 3600)
                return True
            except Exception as exc:
                assert exc.status_code == 429
                return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(12))) == 4


def test_outbox_is_encrypted_rollback_safe_and_erases_delivered_payload(security_site):
    _, factory = security_site
    with factory() as db:
        delivery.enqueue(db, "owner@example.org", "Subject", "very-secret-link", event_key="rolled-back")
        db.rollback()
    with factory() as db:
        assert not db.scalar(select(OutboxEvent))
        event = delivery.enqueue(db, "owner@example.org", "Subject", "very-secret-link", event_key="same-event")
        db.flush()
        assert delivery.enqueue(db, "owner@example.org", "Subject", "very-secret-link", event_key="same-event").id == event.id
        db.commit()
        assert "very-secret-link" not in event.encrypted_payload
        assert "owner@example.org" not in event.encrypted_payload
    ids = delivery.claim_events("worker-1", session_factory=factory)
    assert len(ids) == 1 and delivery.claim_events("worker-2", session_factory=factory) == []
    sent = []
    assert delivery.deliver_one(ids[0], "worker-1", session_factory=factory,
                                sender=lambda payload, key: sent.append((payload, key))) == "SMTP-accepted"
    assert sent[0][0]["body"] == "very-secret-link"
    with factory() as db:
        assert db.get(OutboxEvent, ids[0]).encrypted_payload is None


def test_outbox_retry_crash_recovery_and_consumed_token_never_sends(security_site):
    client, factory = security_site
    client.post("/auth/forgot-password", json={"email": "student@example.org"}, headers=csrf(client))
    raw, event_id = raw_mail_token(factory, "reset_password")
    assert delivery.claim_events("dead-worker", session_factory=factory) == [event_id]
    with factory() as db:
        db.get(OutboxEvent, event_id).lease_until = security.now() - timedelta(seconds=1)
        db.commit()
    assert delivery.claim_events("new-worker", session_factory=factory) == [event_id]
    client.post("/auth/reset-password", json={"token": raw, "password": PASSWORD}, headers=csrf(client))
    sent = []
    assert delivery.deliver_one(event_id, "new-worker", session_factory=factory,
                                sender=lambda *args: sent.append(args)) == "cancelled"
    assert sent == []
    with factory() as db:
        assert db.get(OutboxEvent, event_id).encrypted_payload is None
        assert db.scalar(select(SecurityToken)).used_at is not None


def test_closure_acknowledges_reference_and_erases_without_exposing_answers(security_site):
    client, factory = security_site
    login(client)
    result = client.post("/me/closure", json={"delete": True}, headers=csrf(client))
    assert result.status_code == 202, result.text
    assert result.json()["reference"].startswith("MS-")
    assert client.get("/auth/me").status_code == 401
    with factory() as db:
        user = db.scalar(select(User).where(User.name == "کاربر حذف‌شده"))
        assert user and user.password_hash == "!erased!"
        assert user.account_status == "closed"


def test_report_is_owner_and_operator_only_and_does_not_punish_target(security_site):
    client, factory = security_site
    login(client)
    with factory() as db:
        target = db.scalar(select(User).where(User.email == "second@example.org"))
    created = client.post("/me/reports", json={"target_id": target.id, "category": "harassment", "description": "Review privately"}, headers=csrf(client))
    assert created.status_code == 201
    login(client, "second")
    assert client.get("/me/cases").json()["items"] == []
    assert client.get("/admin/cases").status_code == 403
    with factory() as db:
        assert db.get(User, target.id).is_active


def test_fifty_students_can_request_claims_behind_one_campus_ip(security_site):
    client, factory = security_site
    with factory() as db:
        for index in range(50):
            db.add(Enrollment(student_id=f"campus-{index}", email=f"campus-{index}@example.org", name="Pilot Student",
                              class_name="Math", gender="other", pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE))
        db.commit()
    headers = csrf(client)
    for index in range(50):
        result = client.post("/auth/register", json={"student_id": f"campus-{index}"}, headers=headers)
        assert result.status_code == 202, result.text
    with factory() as db:
        assert len(db.scalars(select(OutboxEvent)).all()) == 50


def test_delivery_retry_boundaries_and_terminal_payload_erasure(security_site, monkeypatch):
    _, factory = security_site
    monkeypatch.setattr(config, "OUTBOX_MAX_ATTEMPTS", 2)
    with factory() as db:
        delivery.enqueue(db, "mail@example.org", "Subject", "Secret", event_key="retry-boundary")
        db.commit()

    def unavailable(*_):
        raise OSError("provider diagnostics must not be persisted")

    event_id = delivery.claim_events("worker", session_factory=factory)[0]
    assert delivery.deliver_one(event_id, "worker", session_factory=factory, sender=unavailable) == "retry-scheduled"
    with factory() as db:
        event = db.get(OutboxEvent, event_id)
        assert event.failure_code == "smtp_unavailable"
        assert security.aware(event.next_attempt_at) >= security.now() + timedelta(seconds=25)
        event.next_attempt_at = security.now() - timedelta(seconds=1)
        db.commit()
    assert delivery.claim_events("worker", session_factory=factory) == [event_id]
    assert delivery.deliver_one(event_id, "worker", session_factory=factory, sender=unavailable) == "terminal-failure"
    with factory() as db:
        event = db.get(OutboxEvent, event_id)
        assert event.encrypted_payload is None and event.attempts == 2


def test_delivery_retry_requires_operator_reason_and_audits_it(security_site):
    client, factory = security_site
    with factory() as db:
        event = delivery.enqueue(db, "student@example.org", "Subject", "private message", event_key="reviewed-retry")
        event.status = "retry-scheduled"
        db.commit()
        event_id = event.id
    endpoint = f"/admin/delivery/{event_id}/retry"
    reason = "Provider recovered and the pending recipient was reviewed"
    login(client)
    assert client.post(endpoint, json={"reason": reason}, headers=csrf(client)).status_code == 403
    login(client, "admin")
    for body in ({}, {"reason": "     "}, {"reason": "tiny"}, {"reason": "x" * 1001}):
        assert client.post(endpoint, json=body, headers=csrf(client)).status_code == 422
    with factory() as db:
        assert db.get(OutboxEvent, event_id).status == "retry-scheduled"
        assert db.scalar(select(DomainAudit).where(DomainAudit.action == "delivery.retry")) is None
    response = client.post(endpoint, json={"reason": f"  {reason}  "}, headers=csrf(client))
    assert response.status_code == 200, response.text
    assert "private message" not in response.text
    with factory() as db:
        assert db.get(OutboxEvent, event_id).status == "pending"
        record = db.scalar(select(DomainAudit).where(DomainAudit.action == "delivery.retry"))
        assert record.reason == reason and record.target_type == "outbox" and record.target_id == event_id
        assert db.get(User, record.actor_id).role == "admin"
    assert client.post(endpoint, json={"reason": reason}, headers=csrf(client)).status_code == 409


def test_auth_logs_and_audit_keep_references_without_credentials(security_site, caplog):
    from main import request_metadata

    _, factory = security_site
    app = FastAPI()
    app.middleware("http")(request_metadata)
    app.include_router(security.router)

    def test_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    caplog.set_level(logging.INFO, logger="matchsho")
    query_secret = "private-query-marker-541891"
    cookie_secret = "private-cookie-marker-620415"
    invalid_token = "private-invalid-token-" * 3
    new_password = "Private-New-Password-397021!"
    request_id = "security-log-audit-01"
    secret_values = [PASSWORD, query_secret, cookie_secret, invalid_token, new_password, "student@example.org"]
    with TestClient(app) as client:
        client.headers["X-Request-ID"] = request_id
        client.cookies.set("unrelated_cookie", cookie_secret)
        assert client.post(f"/auth/login?credential={query_secret}",
                           json={"email": "student@example.org", "password": PASSWORD}, headers=csrf(client)).status_code == 200
        secret_values.extend(cookie.value for cookie in client.cookies.jar)
        assert client.post("/auth/reset-password", json={"token": invalid_token, "password": new_password},
                           headers=csrf(client)).status_code == 400
        assert client.post("/auth/forgot-password", json={"email": "student@example.org"},
                           headers=csrf(client)).status_code == 202
        raw, event_id = raw_mail_token(factory, "reset_password")
        secret_values.append(raw)
        with factory() as db:
            secret_values.append(delivery.decrypt_payload(db.get(OutboxEvent, event_id))["body"].splitlines()[-1])
        assert client.post("/auth/logout", headers=csrf(client)).status_code == 200
        assert client.post("/auth/reset-password", json={"token": raw, "password": new_password},
                           headers=csrf(client)).status_code == 200

    # httpx emits client URLs in its own test transport logs; inspect server loggers.
    messages = [record.getMessage() for record in caplog.records if record.name.startswith("matchsho")]
    logs = "\n".join(messages)
    request_events = [json.loads(message) for message in messages if message.startswith("{")]
    assert any(event["route"] == "/auth/reset-password" and event["status"] == 400 for event in request_events)
    assert all(event["request_id"] == request_id and "?" not in event["route"] for event in request_events)
    for action in ("session.created", "session.logout", "password.reset"):
        assert f"action={action}" in logs and f"request_id={request_id}" in logs
    with factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.target_type == "security")).all()
        assert {row.action for row in rows} == {"session.created", "session.logout", "password.reset"}
        for row in rows:
            assert db.get(User, row.actor_user_id).email == "student@example.org"
            assert row.target_id and row.target_type == "security"
            if row.action.startswith("session."):
                assert db.get(AccountSession, row.target_id).user_id == row.actor_user_id
        audit_text = json.dumps([{column.name: str(getattr(row, column.name)) for column in AuditLog.__table__.columns}
                                 for row in rows])
    assert all(value not in logs and value not in audit_text for value in secret_values)


def test_operator_email_correction_requires_replacement_verification(security_site):
    client, factory = security_site
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.org"))
        enrollment = Enrollment(student_id=user.student_id, email=user.email, name=user.name, class_name=user.class_name,
                                gender=user.gender, pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE, user_id=user.id)
        db.add(enrollment)
        db.commit()
        enrollment_id = enrollment.id
    login(client, "admin")
    result = client.patch(f"/admin/enrollments/{enrollment_id}", json={"field": "email", "value": "replacement@example.org",
                         "reason": "University verified replacement", "dry_run": False}, headers=csrf(client))
    assert result.status_code == 200, result.text
    with factory() as db:
        assert db.get(Enrollment, enrollment_id).email == "student@example.org"
    raw, _ = raw_mail_token(factory, "verify_email")
    assert client.post("/auth/verify-email", json={"token": raw}, headers=csrf(client)).status_code == 200
    with factory() as db:
        assert db.get(Enrollment, enrollment_id).email == "replacement@example.org"


def test_retention_uses_report_creation_and_escalates_open_cases(security_site):
    _, factory = security_site
    from pilot.maintenance import maintenance
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.org"))
        db.add_all([
            SupportCase(reference="expiring", user_id=user.id, kind="report", category="other", description="escalate",
                        created_at=security.now() - timedelta(days=28)),
            SupportCase(reference="expired", user_id=user.id, kind="report", category="other", description="private content",
                        created_at=security.now() - timedelta(days=31)),
        ])
        db.commit()
        maintenance(db)
        db.commit()
        near = db.scalar(select(SupportCase).where(SupportCase.reference == "expiring"))
        old = db.scalar(select(SupportCase).where(SupportCase.reference == "expired"))
        assert near.escalated and near.description == "escalate"
        assert old.description == ""


def test_restore_erasure_requires_quarantine_and_replays_personal_data(security_site, tmp_path, monkeypatch):
    client, factory = security_site
    from pilot.maintenance import export_ledger, replay_ledger
    login(client)
    client.post("/me/closure", json={"delete": True}, headers=csrf(client))
    ledger_file = tmp_path / "erasure-ledger.json"
    with factory() as db:
        assert export_ledger(db, ledger_file) == 1
        with pytest.raises(RuntimeError, match="NO_OUTBOUND_EMAIL"):
            replay_ledger(db, ledger_file)
        user = db.scalar(select(User).where(User.student_id.like("erased-%")))
        user.student_id, user.email, user.name, user.password_hash = "student", "student@example.org", "Restored Name", "restored-hash"
        db.commit()
        monkeypatch.setenv("NO_OUTBOUND_EMAIL", "true")
        assert replay_ledger(db, ledger_file) == 1
        db.commit()
        assert user.email.startswith("erased-") and user.password_hash == "!erased!"


def test_postgres_refresh_race_revokes_the_winning_branch(security_site):
    client, factory = security_site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency test")
    login(client)
    cookies = dict(client.cookies)
    barrier = Barrier(2)

    def rotate():
        with TestClient(client.app) as worker:
            for name, value in cookies.items():
                worker.cookies.set(name, value, domain="testserver.local", path="/")
            barrier.wait(timeout=10)
            result = worker.post("/auth/refresh", headers={"X-CSRF-Token": cookies["csrf_token"]})
            return result.status_code, worker.cookies.get("access_token")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rotate(), range(2)))
    assert sorted(status for status, _ in results) == [200, 401]
    client.cookies.clear()
    winner_token = next(token for status, token in results if status == 200)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {winner_token}"}).status_code == 401


def test_postgres_simultaneous_reset_is_single_use(security_site):
    client, factory = security_site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency test")
    login(client)
    copied_access = client.cookies.get("access_token")
    client.post("/auth/forgot-password", json={"email": "student@example.org"}, headers=csrf(client))
    raw, _ = raw_mail_token(factory, "reset_password")
    cookies = dict(client.cookies)
    barrier = Barrier(2)

    def reset_once():
        with TestClient(client.app) as worker:
            for name, value in cookies.items():
                worker.cookies.set(name, value, domain="testserver.local", path="/")
            barrier.wait(timeout=10)
            return worker.post("/auth/reset-password", json={"token": raw, "password": "New-Race-Password-123!"},
                               headers={"X-CSRF-Token": cookies["csrf_token"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reset_once(), range(2)))
    assert sorted(results) == [200, 400]
    client.cookies.clear()
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {copied_access}"}).status_code == 401


def test_postgres_reset_and_old_password_login_serialize(security_site):
    client, factory = security_site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency test")
    client.post("/auth/forgot-password", json={"email": "student@example.org"}, headers=csrf(client))
    raw, _ = raw_mail_token(factory, "reset_password")
    cookies = dict(client.cookies)
    barrier = Barrier(2)

    def action(kind):
        with TestClient(client.app) as worker:
            for name, value in cookies.items():
                worker.cookies.set(name, value, domain="testserver.local", path="/")
            barrier.wait(timeout=10)
            if kind == "reset":
                result = worker.post("/auth/reset-password", json={"token": raw, "password": "New-Race-Password-123!"},
                                     headers={"X-CSRF-Token": cookies["csrf_token"]})
            else:
                result = worker.post("/auth/login", json={"email": "student@example.org", "password": PASSWORD},
                                     headers={"X-CSRF-Token": cookies["csrf_token"]})
            return kind, result.status_code, worker.cookies.get("access_token")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(action, ("reset", "login")))
    assert next(status for kind, status, _ in results if kind == "reset") == 200
    client.cookies.clear()
    for kind, status, token in results:
        if kind == "login":
            assert status in {200, 401}
            if token:
                assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_postgres_workers_claim_distinct_events_and_smtp_holds_no_connection(security_site):
    _, factory = security_site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL SKIP LOCKED concurrency test")
    with factory() as db:
        for index in range(2):
            delivery.enqueue(db, "student@example.org", "Subject", "Private", event_key=f"parallel-worker:{index}")
        db.commit()
    barrier = Barrier(2)

    def claim(worker):
        barrier.wait(timeout=10)
        return worker, delivery.claim_events(worker, session_factory=factory, limit=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))
    assert len({event for _, events in claims for event in events}) == 2

    def sender(*_):
        assert factory.kw["bind"].pool.checkedout() == 0

    for worker, events in claims:
        assert delivery.deliver_one(events[0], worker, session_factory=factory, sender=sender) == "SMTP-accepted"


def test_ambiguous_smtp_crash_retries_the_same_event_identity(security_site):
    _, factory = security_site
    with factory() as db:
        delivery.enqueue(db, "student@example.org", "Subject", "Private", event_key="ambiguous-smtp")
        db.commit()
    event_id = delivery.claim_events("first-worker", session_factory=factory)[0]
    observed = []

    def crash_after_acceptance(payload, event_key):
        observed.append(event_key)
        raise RuntimeError("simulated process crash after provider acceptance")

    with pytest.raises(RuntimeError):
        delivery.deliver_one(event_id, "first-worker", session_factory=factory, sender=crash_after_acceptance)
    with factory() as db:
        db.get(OutboxEvent, event_id).lease_until = security.now() - timedelta(seconds=1)
        db.commit()
    assert delivery.claim_events("second-worker", session_factory=factory) == [event_id]
    assert delivery.deliver_one(event_id, "second-worker", session_factory=factory,
                                sender=lambda payload, key: observed.append(key)) == "SMTP-accepted"
    assert observed == ["ambiguous-smtp", "ambiguous-smtp"]


def test_forwarded_headers_cannot_change_application_throttle_identity(security_site, monkeypatch):
    client, _ = security_site
    monkeypatch.setattr(config, "LOGIN_IP_LIMIT", 2)
    for index in range(3):
        response = client.post("/auth/login", json={"email": f"unknown-{index}@example.org", "password": "wrong"},
                               headers={**csrf(client), "X-Forwarded-For": f"192.0.2.{index}", "X-Real-IP": f"198.51.100.{index}"})
        assert response.status_code == (401 if index < 2 else 429)


def test_limiter_storage_failure_is_retryable_and_does_not_authenticate(security_site):
    client, factory = security_site
    with factory.kw["bind"].begin() as connection:
        connection.execute(text("DROP TABLE pilot_rate_buckets"))
    result = client.post("/auth/login", json={"email": "student@example.org", "password": PASSWORD}, headers=csrf(client))
    assert result.status_code == 503 and result.headers["Retry-After"] == "30"
    assert client.get("/auth/me").status_code == 401


def test_closed_deactivation_resolves_after_individual_departure(security_site):
    _, factory = security_site
    from pilot.maintenance import process_closures
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "student@example.org"))
        user.account_status, user.is_active = "pending-closure", False
        case = SupportCase(reference="deactivation-after-departure", user_id=user.id, kind="closure",
                           category="deactivation", description="", status="open")
        db.add(case)
        db.commit()
        assert process_closures(db) == 1
        db.commit()
        assert user.account_status == "closed" and case.status == "resolved"
        assert user.email == "student@example.org"


@pytest.mark.parametrize("change", ["demotion", "suspension", "session_revocation"])
def test_postgres_mutation_rechecks_authority_after_waiting(security_site, monkeypatch, change):
    client, factory = security_site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL authorization and advisory-lock ordering test")
    from pilot import domain_events
    login(client, "admin" if change == "demotion" else "student")
    cookies = dict(client.cookies)
    waiting = Event()
    original_before = domain_events.before_mutation

    def observing_before(db):
        waiting.set()
        original_before(db)

    monkeypatch.setattr(domain_events, "before_mutation", observing_before)

    def request_mutation():
        with TestClient(client.app) as worker:
            for name, value in cookies.items():
                worker.cookies.set(name, value, domain="testserver.local", path="/")
            headers = {"X-CSRF-Token": cookies["csrf_token"]}
            if change == "demotion":
                return worker.post("/admin/users/1/security", json={"action": "revoke_sessions", "reason": "Reviewed security event"},
                                   headers=headers).status_code
            return worker.patch("/me/profile", json={"name": "Should Not Change", "class_name": "Math"}, headers=headers).status_code

    with factory() as gate:
        original_before(gate)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(request_mutation)
            assert waiting.wait(timeout=15)
            user = gate.scalar(select(User).where(User.email == ("admin@example.org" if change == "demotion" else "student@example.org")))
            if change == "demotion":
                user.role = "user"
            elif change == "suspension":
                user.is_active, user.account_status = False, "suspended"
            else:
                security.revoke_all(gate, user)
            gate.commit()
            assert future.result(timeout=20) == (403 if change == "demotion" else 401)
    with factory() as db:
        assert not db.scalar(select(User).where(User.name == "Should Not Change"))


def test_reviewed_legacy_email_rebind_requires_recipient_claim(security_site):
    client, factory = security_site
    with factory() as db:
        legacy = db.scalar(select(User).where(User.student_id == "student"))
        legacy.email_verified = False
        legacy_id, original_hash = legacy.id, legacy.password_hash
        db.commit()
    login(client, "admin")
    row = {"student_id": "student", "email": "official-address@example.org", "name": "University Roster Name",
           "class_name": "Math", "gender": "other", "pool": config.ALLOWED_POOLS[0], "cycle": config.ACTIVE_CYCLE}
    payload = {"rows": [row], "dry_run": True, "reason": "Official roster confirms corrected legacy email"}
    preview = client.post("/admin/roster/import", json=payload, headers=csrf(client)).json()
    assert not preview["valid"] and preview["impacts"][0]["user_id"] == legacy_id
    payload.update(allow_legacy_email_rebind=True, dry_run=False)
    imported = client.post("/admin/roster/import", json=payload, headers=csrf(client))
    assert imported.json()["imported"] == 1
    with factory() as db:
        legacy = db.get(User, legacy_id)
        assert legacy.email == "student@example.org" and legacy.password_hash == original_hash
        assert db.scalar(select(Enrollment)).user_id is None
    client.cookies.clear()
    assert client.post("/auth/register", json={"student_id": "student"}, headers=csrf(client)).status_code == 202
    raw, _ = raw_mail_token(factory, "claim")
    result = client.post("/auth/activate", json={"token": raw, "password": "New-Approved-Credential-123!"}, headers=csrf(client))
    assert result.status_code == 200 and result.json()["id"] == legacy_id
    assert result.json()["email"] == "official-address@example.org"


def test_legacy_rebind_flag_cannot_replace_a_verified_account(security_site):
    client, factory = security_site
    login(client, "admin")
    row = {"student_id": "student", "email": "replacement@example.org", "name": "Same Identity", "class_name": "Math",
           "gender": "other", "pool": config.ALLOWED_POOLS[0], "cycle": config.ACTIVE_CYCLE}
    result = client.post("/admin/roster/import", json={"rows": [row], "dry_run": False, "reason": "Reviewed import attempt",
                         "allow_legacy_email_rebind": True}, headers=csrf(client))
    assert not result.json()["valid"] and result.json()["imported"] == 0
    with factory() as db:
        assert not db.scalar(select(Enrollment))


def test_claim_cannot_reactivate_a_suspended_unbound_legacy_account(security_site):
    client, factory = security_site
    with factory() as db:
        user = db.scalar(select(User).where(User.student_id == "student"))
        user.email_verified = False
        db.add(Enrollment(student_id=user.student_id, email=user.email, name=user.name, class_name=user.class_name,
                          gender=user.gender, pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE))
        db.commit()
    client.post("/auth/register", json={"student_id": "student"}, headers=csrf(client))
    raw, _ = raw_mail_token(factory, "claim")
    with factory() as db:
        user = db.scalar(select(User).where(User.student_id == "student"))
        user.is_active, user.account_status = False, "suspended"
        db.commit()
    result = client.post("/auth/activate", json={"token": raw, "password": PASSWORD}, headers=csrf(client))
    assert result.status_code == 400
    with factory() as db:
        assert db.scalar(select(User).where(User.student_id == "student")).account_status == "suspended"


def test_block_list_cannot_lookup_unavailable_student_identity(security_site):
    client, factory = security_site
    login(client)
    with factory() as db:
        target = db.scalar(select(User).where(User.student_id == "second"))
    result = client.post(f"/me/blocks/{target.id}", headers=csrf(client))
    assert result.status_code == 404
    assert client.get("/me/blocks").json()["items"] == []


def test_postgres_limiter_does_not_need_a_second_business_pool_slot(security_site):
    _, factory = security_site
    source = factory.kw["bind"]
    if source.dialect.name != "postgresql":
        pytest.skip("PostgreSQL independent pool pressure test")
    with source.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    limited = create_engine(source.url, connect_args={"options": f"-csearch_path={schema}"},
                            pool_size=1, max_overflow=0, pool_timeout=0.2)
    limited.rate_limit_bind = source.rate_limit_bind
    try:
        with Session(bind=limited) as business:
            from pilot.domain_events import before_mutation
            before_mutation(business)
            assert limited.pool.checkedout() == 1
            security.throttle(business, "pool-pressure", "one", 1, 3600)
            business.rollback()
        with factory() as db:
            assert db.scalar(select(RateBucket.attempts)) == 1
    finally:
        limited.dispose()


def test_hash_and_verify_share_the_memory_concurrency_cap(monkeypatch):
    lock = Lock()
    active = peak = 0

    class MeasuredHasher:
        def _work(self):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(active, peak)
            time.sleep(0.02)
            with lock:
                active -= 1

        def hash(self, value):
            self._work()
            return "hash"

        def verify(self, stored, value):
            self._work()
            return True

    monkeypatch.setattr(security, "password_hasher", MeasuredHasher())
    monkeypatch.setattr(security, "_argon2_slots", BoundedSemaphore(2))

    def work(index):
        return security.hash_password("value") if index % 2 else security.verify_password("hash", "value")

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert len(list(executor.map(work, range(16)))) == 16
    assert peak == 2 and active == 0


def test_assigned_deletion_keeps_other_bed_until_individual_exit(security_site):
    client, factory = security_site
    from pilot.domain_events import before_mutation, remove_member
    from pilot.domain_models import Departure
    from pilot.maintenance import process_closures
    with factory() as db:
        owner = db.scalar(select(User).where(User.student_id == "student"))
        other = db.scalar(select(User).where(User.student_id == "second"))
        group = Group(capacity=2, pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE, reconciliation_required=False)
        room = Room(number="closure-test", dormitory="Test", capacity=2, current_occupancy=2,
                    pool=config.ALLOWED_POOLS[0], cycle=config.ACTIVE_CYCLE, reconciliation_required=False)
        db.add_all([group, room])
        db.flush()
        db.add_all([GroupMember(user_id=owner.id, group_id=group.id), GroupMember(user_id=other.id, group_id=group.id),
                    RoomAssignment(group_id=group.id, room_id=room.id)])
        db.commit()
        owner_id, other_id, room_id, group_id = owner.id, other.id, room.id, group.id
    login(client)
    response = client.post("/me/closure", json={"delete": True}, headers=csrf(client))
    assert response.status_code == 202 and response.json()["reference"]
    with factory() as db:
        assert db.get(User, owner_id).account_status == "pending-closure"
        assert db.get(Room, room_id).current_occupancy == 2
        assert db.query(GroupMember).filter_by(group_id=group_id).count() == 2
        assert db.scalar(select(Departure).where(Departure.user_id == owner_id)).status == "pending"
        before_mutation(db)
        remove_member(db, db.get(User, owner_id), None, "Reviewed individual operational exit")
        assert process_closures(db) == 1
        db.commit()
        assert db.get(Room, room_id).current_occupancy == 1
        assert db.scalar(select(GroupMember).where(GroupMember.user_id == other_id)).group_id == group_id
        assert db.scalar(select(RoomAssignment).where(RoomAssignment.group_id == group_id)).room_id == room_id
        assert db.get(User, owner_id).account_status == "closed"
        assert db.get(User, other_id).is_active
