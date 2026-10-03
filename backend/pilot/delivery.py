"""Transactional encrypted outbox with durable, recoverable delivery leases."""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import and_, func, or_, select

from database import SessionLocal
from models import User
from pilot import config
from pilot.security import aware, keyed_digest, now, usable_token
from pilot.security_models import DeletionLedger, Enrollment, OutboxEvent, SecurityToken, WorkerHeartbeat

SENDABLE = ("pending", "retry-scheduled", "leased")
TERMINAL = ("SMTP-accepted", "expired", "cancelled", "terminal-failure")


def enqueue(db, recipient, subject, body, *, event_key, purpose="notification", token_id=None):
    """Enqueue inside the caller's transaction; this function never commits."""
    for pending in db.new:
        if isinstance(pending, OutboxEvent) and pending.event_key == event_key:
            return pending
    existing = db.scalar(select(OutboxEvent).where(OutboxEvent.event_key == event_key))
    if existing:
        return existing
    token = db.get(SecurityToken, token_id) if token_id else None
    expiry = aware(token.expires_at) if token else now() + timedelta(days=1)
    payload = json.dumps({"recipient": recipient, "subject": subject, "body": body,
                          "event_key": event_key, "expiry": expiry.isoformat()}, ensure_ascii=False)
    event = OutboxEvent(event_key=event_key, purpose=purpose, token_id=token_id,
                        recipient_ref=keyed_digest(recipient.strip().lower()),
                        key_version=config.OUTBOX_KEY_VERSION,
                        encrypted_payload=Fernet(config.OUTBOX_KEYS[config.OUTBOX_KEY_VERSION].encode()).encrypt(payload.encode()).decode(),
                        expires_at=expiry, status="pending", next_attempt_at=now())
    db.add(event)
    return event


def decrypt_payload(event):
    key = config.OUTBOX_KEYS.get(event.key_version)
    if not key or not event.encrypted_payload:
        raise ValueError("payload_unavailable")
    try:
        payload = json.loads(Fernet(key.encode()).decrypt(event.encrypted_payload.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise ValueError("payload_invalid") from None
    if payload.get("event_key") != event.event_key or payload.get("expiry") != aware(event.expires_at).isoformat():
        raise ValueError("envelope_mismatch")
    if keyed_digest(payload.get("recipient", "").strip().lower()) != event.recipient_ref:
        raise ValueError("recipient_mismatch")
    return payload


def eligibility(db, event, payload):
    if event.purpose in {"claim", "reset_password", "verify_email"} and not config.REQUIRE_EMAIL_VERIFICATION:
        return "cancelled"
    if aware(event.expires_at) <= now():
        return "expired"
    if not event.token_id:
        return None
    token = db.get(SecurityToken, event.token_id)
    if not usable_token(token, event.purpose):
        return "expired" if token and aware(token.expires_at) <= now() else "cancelled"
    if token.approved_email != payload["recipient"]:
        return "cancelled"
    if token.purpose == "claim":
        enrollment = db.get(Enrollment, token.enrollment_id)
        if (not enrollment or enrollment.status != "eligible" or enrollment.email != token.approved_email
                or enrollment.cycle != config.ACTIVE_CYCLE or enrollment.pool not in config.ALLOWED_POOLS):
            return "cancelled"
        account = db.get(User, enrollment.user_id) if enrollment.user_id else db.scalar(
            select(User).where(User.student_id == enrollment.student_id))
        if account:
            if (account.role != "user" or not account.is_active or account.account_status != "active"
                    or db.get(DeletionLedger, account.id)):
                return "cancelled"
            if enrollment.user_id and account.email_verified:
                return "cancelled"
    else:
        account = db.get(User, token.user_id)
        if not account or not account.is_active or account.account_status != "active":
            return "cancelled"
        if token.purpose != "verify_email" and account.email != token.approved_email:
            return "cancelled"
        if token.purpose == "verify_email":
            enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == account.id))
            if not enrollment or enrollment.status != "eligible":
                return "cancelled"
    return None


def finish(event, status, failure=None):
    event.status, event.failure_code = status, failure
    event.lease_owner, event.lease_until = None, None
    if status in TERMINAL:
        event.encrypted_payload = None
        event.finished_at = now()


def claim_events(worker_id, *, session_factory=SessionLocal, limit=10):
    if os.getenv("NO_OUTBOUND_EMAIL", "false").lower() == "true":
        return []
    with session_factory() as db:
        instant = now()
        heartbeat = db.get(WorkerHeartbeat, worker_id)
        if heartbeat:
            heartbeat.last_seen_at = instant
        else:
            db.add(WorkerHeartbeat(worker_id=worker_id, last_seen_at=instant))
        events = db.scalars(select(OutboxEvent).where(
            or_(and_(OutboxEvent.status.in_(("pending", "retry-scheduled")), OutboxEvent.next_attempt_at <= instant),
                and_(OutboxEvent.status == "leased", OutboxEvent.lease_until <= instant)))
            .order_by(OutboxEvent.created_at, OutboxEvent.id).limit(min(limit, 100)).with_for_update(skip_locked=True)).all()
        claimed = []
        for event in events:
            if aware(event.expires_at) <= instant:
                finish(event, "expired")
            elif event.attempts >= config.OUTBOX_MAX_ATTEMPTS:
                finish(event, "terminal-failure", "attempts_exhausted")
            else:
                event.status = "leased"
                event.lease_owner, event.lease_until = worker_id, instant + timedelta(seconds=config.OUTBOX_LEASE_SECONDS)
                event.attempts += 1
                claimed.append(event.id)
        db.commit()
        return claimed


def smtp_send(payload, event_key):
    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM", "matchsho@localhost")
    message["To"] = payload["recipient"]
    message["Subject"] = payload["subject"]
    message["Message-ID"] = f"<{keyed_digest(event_key)}@matchsho.outbox>"
    message.set_content(payload["body"])
    host = os.getenv("SMTP_HOST", "localhost")
    security = os.getenv("SMTP_SECURITY", "starttls" if config.ENVIRONMENT == "production" else "none")
    port = int(os.getenv("SMTP_PORT", "465" if security == "tls" else "1025"))
    context = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=context) if security == "tls" else smtplib.SMTP(host, port, timeout=20)
    with smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        username = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", ""))
        if username:
            smtp.login(username, os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(message)


def deliver_one(event_id, worker_id, *, session_factory=SessionLocal, sender=smtp_send):
    """SMTP runs after closing the read transaction. Completion checks lease ownership."""
    if os.getenv("NO_OUTBOUND_EMAIL", "false").lower() == "true":
        return "disabled"
    with session_factory() as db:
        event = db.get(OutboxEvent, event_id)
        if (not event or event.status != "leased" or event.lease_owner != worker_id
                or aware(event.lease_until) <= now()):
            return "lost-lease"
        try:
            payload = decrypt_payload(event)
            invalid = eligibility(db, event, payload)
        except ValueError:
            payload, invalid = None, "terminal-failure"
        event_key = event.event_key
        if invalid:
            # Own the row through finalization; another worker cannot erase a live lease.
            event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id)
                              .execution_options(populate_existing=True).with_for_update())
            if event.lease_owner == worker_id and event.status == "leased":
                finish(event, invalid, "payload_or_binding_invalid" if invalid == "terminal-failure" else None)
                db.commit()
            return invalid
    status, failure = "SMTP-accepted", None
    try:
        sender(payload, event_key)
    except smtplib.SMTPRecipientsRefused as exc:
        # Provider strings may contain recipient addresses or secrets; retain only category.
        permanent = all(int(value[0]) >= 500 for value in exc.recipients.values())
        status, failure = ("terminal-failure" if permanent else "retry-scheduled"), "recipient_rejected"
    except smtplib.SMTPResponseException as exc:
        status, failure = ("terminal-failure" if exc.smtp_code >= 500 else "retry-scheduled"), "smtp_rejected"
    except (OSError, smtplib.SMTPException):
        status, failure = "retry-scheduled", "smtp_unavailable"
    with session_factory() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update())
        if event.status != "leased" or event.lease_owner != worker_id or aware(event.lease_until) <= now():
            return "lost-lease"
        if status == "retry-scheduled":
            if event.attempts >= config.OUTBOX_MAX_ATTEMPTS:
                status = "terminal-failure"
            else:
                event.next_attempt_at = now() + timedelta(seconds=min(900, 30 * 2 ** (event.attempts - 1)))
        finish(event, status, failure)
        db.commit()
    return status


def health(db):
    heartbeat = db.scalar(select(func.max(WorkerHeartbeat.last_seen_at)))
    oldest = db.scalar(select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status.in_(SENDABLE)))
    age = int((now() - aware(oldest)).total_seconds()) if oldest else 0
    failures = db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "terminal-failure"))
    alerts = []
    if not heartbeat or now() - aware(heartbeat) > timedelta(minutes=2):
        alerts.append("worker_missing")
    if age > 300:
        alerts.append("queue_age_exceeded")
    if failures:
        alerts.append("terminal_delivery_failure")
    return {"last_heartbeat_at": heartbeat, "oldest_pending_age_seconds": age,
            "pending_count": db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status.in_(SENDABLE))),
            "retry_count": db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "retry-scheduled")),
            "terminal_failures": failures, "alerts": alerts}
