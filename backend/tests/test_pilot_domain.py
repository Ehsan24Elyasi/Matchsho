"""Behavior/invariant regression tests using isolated SQLite and PostgreSQL schemas."""
import copy
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from models import Group, GroupMember, Room, RoomAssignment, User
from pilot import config, housing, invitations, questionnaire, security
from pilot.domain_events import before_mutation, members, occupancy
from pilot.domain_models import Departure, Invitation, Notification, Questionnaire
from pilot.matching import MatchingContext
from pilot.preflight import report
from pilot.security_models import Enrollment, OutboxEvent, UserBlock
from tests.pg_race import race


def answers():
    return {"sleep": {"own": "23:00", "accepted": ["22:00", "01:00"], "importance": 2, "hard": False},
            "wake": {"own": "07:00", "accepted": ["06:00", "09:00"], "importance": 2, "hard": False},
            "cleaning": {"own": "weekly", "accepted": ["weekly", "daily"], "importance": 2, "hard": False},
            "guests": {"own": "never", "accepted": ["never"], "importance": 2, "hard": False},
            "noise": {"own": "quiet", "accepted": ["quiet"], "importance": 2, "hard": False}}


@pytest.fixture(params=["sqlite", "postgresql"])
def site(request, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ACTIVE_CYCLE", "pilot-2026")
    monkeypatch.setattr(config, "ALLOWED_POOLS", ("male", "female"))
    if request.param == "postgresql":
        url = os.getenv("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL is required for actual PostgreSQL evidence")
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql" and parsed.database.endswith("_test"), "Disposable _test DB required"
        schema = "test_domain_" + uuid.uuid4().hex
        control = create_engine(url)
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=20000"})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'domain-only.sqlite3'}", connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi, _):
            dbapi.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with factory() as db:
        for uid in range(1, 10):
            u = User(id=uid, email=f"student{uid}@example.org", name=f"دانشجو {uid}", class_name="مهندسی",
                     student_id=f"fixture{uid}", gender="male", role="admin" if uid == 9 else "user",
                     password_hash="!test-only!", email_verified=True, discovery_consent=True, explanation_consent=True)
            db.add(u)
        db.flush()
        for uid in range(1, 9):
            db.add(Enrollment(user_id=uid, student_id=f"fixture{uid}", email=f"student{uid}@example.org",
                name=f"دانشجو {uid}", class_name="مهندسی", gender="male", pool="female" if uid == 8 else "male", cycle="pilot-2026"))
            db.add(Questionnaire(user_id=uid, answers=answers(), capacities=[2, 4], revision=1, complete=True))
        for rid, capacity, pool in [(1, 4, "male"), (2, 4, "male"), (3, 2, "male"), (4, 4, "female")]:
            db.add(Room(id=rid, number=str(rid), dormitory="پایلوت", pool=pool, cycle="pilot-2026", capacity=capacity,
                        reconciliation_required=False))
        db.commit()

    def session():
        with factory() as db:
            yield db

    def test_user(request: Request, db=Depends(get_db)):
        return db.get(User, int(request.headers.get("X-Test-User", "1")))

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[security.current_user] = test_user
    app.dependency_overrides[security.require_csrf] = lambda: None
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()
    if request.param == "postgresql":
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def api(client, method, path, actor=1, body=None, expected=200):
    response = client.request(method, path, headers={"X-Test-User": str(actor)}, json=body)
    assert response.status_code == expected, response.text
    return response.json() if response.content else None


def create(client, receiver, actor=1, capacity=4):
    return api(client, "POST", "/requests", actor, {"receiver_id": receiver, "capacity": capacity})


def form_group(client, first=1, second=2):
    inv = create(client, second, first)
    result = api(client, "POST", f"/requests/{inv['id']}/approve", second)
    assert result["status"] == "accepted"
    return api(client, "GET", "/group/me", first)["id"]


def test_questionnaire_behavior_not_importance_and_midnight():
    a, b = answers(), answers()
    assert questionnaire.alignment(a, b)[0] == 100
    b["sleep"]["own"] = "02:00"
    assert questionnaire.alignment(a, b)[0] == 90
    b["sleep"]["own"] = "00:30"
    assert questionnaire.alignment(a, b)[0] == 100
    a["sleep"]["hard"] = True
    b["sleep"]["own"] = "02:00"
    assert questionnaire.alignment(a, b)[0] is None
    a["tobacco"] = {"own": None, "accepted": ["never"], "importance": 3, "hard": True}
    assert questionnaire.alignment(a, answers())[0] is None
    left = {"noise": {"own": "quiet", "accepted": ["music"], "importance": 1},
            "guests": {"own": "never", "accepted": ["never"], "importance": 1}}
    right = {"noise": {"own": "music", "accepted": ["headphones"], "importance": 3},
             "guests": {"own": "weekly", "accepted": ["daily"], "importance": 3}}
    assert questionnaire.alignment(left, right)[0] == 13  # 12.5 rounds up, not bankers' 12.


def test_peer_privacy_consent_pool_block_and_same_group_history(site):
    client, factory = site
    result = api(client, "GET", "/matches")
    assert result["total"] == 6
    assert 8 not in [item["id"] for item in result["items"]]
    assert "student_id" not in str(result) and "@example" not in str(result) and "answers" not in str(result)
    with factory() as db:
        db.get(User, 2).explanation_consent = False
        db.add(UserBlock(actor_id=3, target_id=1))
        db.commit()
    result = api(client, "GET", "/matches")
    assert next(item for item in result["items"] if item["id"] == 2)["explanations"] == []
    assert 3 not in [item["id"] for item in result["items"]]
    api(client, "GET", "/profiles/3", expected=404)
    gid = form_group(client)
    api(client, "POST", f"/admin/groups/{gid}/allocation", 9, {"room_id": 1, "reason": "تخصیص آزمایشی"})
    peer = api(client, "GET", "/profiles/2")
    assert peer["can_invite"] is False and peer["score"] is None
    assert "@example" not in str(peer) and "student_id" not in str(peer)
    assert api(client, "GET", "/matches")["items"] == []
    with factory() as db:
        db.add(UserBlock(actor_id=2, target_id=1))
        db.commit()
    api(client, "GET", "/profiles/2", expected=404)
    assert len(api(client, "GET", "/group/me")["members"]) == 2


@pytest.mark.parametrize("key,value", [("own", {}), ("accepted", [{}]), ("importance", True)])
def test_malformed_questionnaire_returns_validation_error(key, value):
    submitted = answers()
    submitted["cleaning"][key] = value
    with pytest.raises(HTTPException) as exc:
        questionnaire.validate_answers(questionnaire.Submission(answers=submitted, capacities=[4]))
    assert exc.value.status_code == 422


def test_draft_does_not_publish_and_submit_invalidates(site):
    client, factory = site
    inv = create(client, 2)
    partial = {"version": 2, "answers": {"sleep": {"own": None, "accepted": ["", ""]}}, "capacities": []}
    api(client, "PUT", "/questionnaire/draft", body=partial)
    assert api(client, "GET", "/questionnaire/me")["revision"] == 1
    assert api(client, "GET", "/questionnaire/draft")["answers"] == partial["answers"]
    api(client, "PUT", "/questionnaire/me", body={"version": 2, "answers": answers(), "capacities": [4]})
    api(client, "POST", f"/requests/{inv['id']}/approve", 2, expected=409)
    renewed = api(client, "POST", f"/requests/{inv['id']}/reconfirm", 2)
    assert renewed["approvals"] == [] and renewed["expires_at"] == inv["expires_at"]
    api(client, "POST", f"/requests/{inv['id']}/approve", 2)
    accepted = api(client, "POST", f"/requests/{inv['id']}/approve", 1)
    assert accepted["status"] == "accepted"


def test_unanimous_admission_and_other_proposal_reconfirmation(site):
    client, factory = site
    gid = form_group(client)
    first, second = create(client, 3), create(client, 4)
    api(client, "POST", f"/requests/{first['id']}/approve", 3)
    assert api(client, "GET", "/group/me")["members"] == [
        {"id": 1, "name": "دانشجو 1", "class_name": "مهندسی"}, {"id": 2, "name": "دانشجو 2", "class_name": "مهندسی"}]
    api(client, "POST", f"/requests/{first['id']}/approve", 2)
    requests = api(client, "GET", "/requests")["items"]
    assert next(x for x in requests if x["id"] == second["id"])["status"] == "needs_reconfirmation"
    renewed = api(client, "POST", f"/requests/{second['id']}/reconfirm")
    assert renewed["required_approvals"] == [1, 2, 3, 4]
    for uid in (1, 2, 3, 4):
        outcome = api(client, "POST", f"/requests/{second['id']}/approve", uid)
    assert outcome["status"] == "accepted"
    assert len(api(client, "GET", "/group/me")["members"]) == 4
    with factory() as db:
        assert db.query(Group).count() == 1 and db.get(Group, gid).is_complete


def test_terminal_idempotency_expiry_and_atomic_outbox(site):
    client, factory = site
    inv = create(client, 2)
    api(client, "POST", f"/requests/{inv['id']}/approve", 2)
    with factory() as db:
        notices, emails = db.query(Notification).count(), db.query(OutboxEvent).count()
    api(client, "POST", f"/requests/{inv['id']}/approve", 2)
    api(client, "POST", f"/requests/{inv['id']}/cancel", expected=409)
    with factory() as db:
        assert db.query(Notification).count() == notices and db.query(OutboxEvent).count() == emails
        assert db.query(GroupMember).count() == 2
    expired = create(client, 4, actor=3)
    with factory() as db:
        db.get(Invitation, expired["id"]).expires_at = security.now() - timedelta(seconds=1)
        db.commit()
    api(client, "POST", f"/requests/{expired['id']}/approve", 4, expected=409)
    assert create(client, 4, actor=3)["id"] != expired["id"]


def test_individual_departure_preserves_room_and_last_removal(site):
    client, factory = site
    gid = form_group(client)
    api(client, "POST", f"/admin/groups/{gid}/allocation", 9, {"room_id": 1, "reason": "تخصیص آزمایشی"})
    api(client, "DELETE", "/group/me", expected=409)
    api(client, "DELETE", f"/admin/groups/{gid}/allocation", body={"reason": "نامعتبر"}, expected=403)
    dep = api(client, "POST", "/group/me/departure", body={"reason": "خروج از خوابگاه"})
    payload = {"decision": "approved", "reason": "تحویل اتاق تأیید شد"}
    api(client, "POST", f"/admin/departures/{dep['id']}/resolve", 9, payload)
    api(client, "POST", f"/admin/departures/{dep['id']}/resolve", 9, payload)
    with factory() as db:
        assert occupancy(db, 1) == db.get(Room, 1).current_occupancy == 1
        assert [u.id for u in members(db, gid)] == [2]
    api(client, "DELETE", f"/admin/groups/{gid}/members/2", 9, {"reason": "خروج عضو باقی‌مانده"})
    with factory() as db:
        assert db.get(Group, gid) is None
        assert db.query(RoomAssignment).count() == 0 and db.get(Room, 1).current_occupancy == 0
        assert db.get(Departure, dep["id"]).status == "approved"


def test_room_guards_move_rollback_suspension_and_reconciliation(site):
    client, factory = site
    g1, g2 = form_group(client), form_group(client, 3, 4)
    api(client, "POST", f"/admin/groups/{g1}/allocation", 9, {"room_id": 3, "reason": "ظرفیت متفاوت"}, 409)
    api(client, "POST", f"/admin/groups/{g1}/allocation", 9, {"room_id": 4, "reason": "محدودهٔ متفاوت"}, 409)
    api(client, "POST", f"/admin/groups/{g1}/allocation", 9, {"room_id": 1, "reason": "تخصیص نخست"})
    api(client, "POST", f"/admin/groups/{g2}/allocation", 9, {"room_id": 1, "reason": "گروه مستقل"}, 409)
    api(client, "POST", f"/admin/groups/{g2}/allocation", 9, {"room_id": 2, "reason": "تخصیص دوم"})
    api(client, "POST", f"/admin/groups/{g1}/allocation", 9, {"room_id": 2, "reason": "انتقال ناممکن"}, 409)
    with factory() as db:
        db.get(User, 1).account_status, db.get(User, 1).is_active = "suspended", False
        db.commit()
        assert occupancy(db, 1) == 2
        assert db.query(RoomAssignment).filter_by(group_id=g1).one().room_id == 1
        before = db.query(GroupMember).count()
        result = report(db.connection())
        assert result["ok"]
        assert db.query(GroupMember).count() == before


def test_score_group_minimum_consent_and_pending_closure(site):
    client, factory = site
    gid = form_group(client)
    with factory() as db:
        q = db.get(Questionnaire, 2)
        changed = copy.deepcopy(q.answers)
        changed["sleep"]["own"] = "02:00"
        q.answers = changed
        db.get(User, 2).explanation_consent = False
        db.commit()
    result = api(client, "GET", "/matches", 3)
    group = next(x for x in result["items"] if x["kind"] == "group")
    assert group["score"] == 90 and group["explanations"] == []
    with factory() as db:
        db.get(User, 2).account_status = "pending-closure"
        db.commit()
    assert all(x["kind"] != "group" for x in api(client, "GET", "/matches", 3)["items"])
    api(client, "POST", "/requests", 3, {"group_id": gid, "capacity": 4}, 409)


@pytest.mark.parametrize("left_action,left_actor,right_action,right_actor", [
    ("approve", 2, "cancel", 1),
    ("approve", 2, "reject", 2),
    ("reject", 2, "cancel", 1),
])
def test_postgresql_accept_cancel_single_winner(site, left_action, left_actor, right_action, right_actor):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    inv = create(client, 2)
    outcomes = race(factory,
        lambda db: invitations.transition(inv["id"], left_action, db.get(User, left_actor), db),
        lambda db: invitations.transition(inv["id"], right_action, db.get(User, right_actor), db))
    assert sum(isinstance(x, dict) for x in outcomes) == 1, outcomes
    assert sum(isinstance(x, HTTPException) and x.status_code == 409 for x in outcomes) == 1, outcomes
    with factory() as db:
        state = db.get(Invitation, inv["id"]).status
        assert db.query(GroupMember).count() == (2 if state == "accepted" else 0)


def test_postgresql_last_place_and_allocation_races(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    gid = form_group(client)
    third = create(client, 3)
    for uid in (2, 3):
        api(client, "POST", f"/requests/{third['id']}/approve", uid)
    left, right = create(client, 4), create(client, 5)
    for inv in (left, right):
        for uid in (2, 3):
            api(client, "POST", f"/requests/{inv['id']}/approve", uid)
    outcomes = race(factory,
        lambda db: invitations.transition(left["id"], "approve", db.get(User, 4), db),
        lambda db: invitations.transition(right["id"], "approve", db.get(User, 5), db))
    assert sum(isinstance(x, dict) and x["status"] == "accepted" for x in outcomes) == 1, outcomes
    assert any(isinstance(x, HTTPException) and x.status_code == 409 for x in outcomes), outcomes
    with factory() as db:
        assert len(members(db, gid)) == 4
        assert db.query(Invitation).filter_by(status="accepted").count() == 3


def test_postgresql_allocation_competition_and_admission(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    g1, g2 = form_group(client), form_group(client, 3, 4)
    request = SimpleNamespace(state=SimpleNamespace(request_id="test-race"), headers={})
    payload = housing.Allocation(room_id=1, reason="آزمون هم‌زمانی")
    outcomes = race(factory,
        lambda db: housing.allocate(g1, payload, request, db.get(User, 9), db),
        lambda db: housing.allocate(g2, payload, request, db.get(User, 9), db))
    assert sum(isinstance(x, dict) for x in outcomes) == 1, outcomes
    assert any(isinstance(x, HTTPException) and x.status_code == 409 for x in outcomes), outcomes
    with factory() as db:
        assert db.query(RoomAssignment).filter_by(room_id=1).count() == 1
        assert db.get(Room, 1).current_occupancy == occupancy(db, 1) == 2


def test_postgresql_admission_races_allocation(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    gid = form_group(client)
    inv = create(client, 3)
    api(client, "POST", f"/requests/{inv['id']}/approve", 3)
    request = SimpleNamespace(state=SimpleNamespace(request_id="allocation-admission-race"), headers={})
    outcomes = race(factory,
        lambda db: invitations.transition(inv["id"], "approve", db.get(User, 2), db),
        lambda db: housing.allocate(gid, housing.Allocation(room_id=1, reason="تخصیص هم‌زمان"), request, db.get(User, 9), db))
    assert isinstance(outcomes[1], dict), outcomes
    assert isinstance(outcomes[0], dict) or isinstance(outcomes[0], HTTPException) and outcomes[0].status_code == 409, outcomes
    with factory() as db:
        size = len(members(db, gid))
        assert size in (2, 3) and occupancy(db, 1) == db.get(Room, 1).current_occupancy == size
        assert db.get(Invitation, inv["id"]).status == ("accepted" if size == 3 else "cancelled")


def test_postgresql_departure_races_allocation(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    gid = form_group(client)
    request = SimpleNamespace(state=SimpleNamespace(request_id="departure-allocation-race"), headers={})
    outcomes = race(factory,
        lambda db: housing.leave_group(db.get(User, 2), db),
        lambda db: housing.allocate(gid, housing.Allocation(room_id=1, reason="تخصیص هم‌زمان"), request, db.get(User, 9), db))
    assert isinstance(outcomes[1], dict), outcomes
    assert isinstance(outcomes[0], dict) or isinstance(outcomes[0], HTTPException) and outcomes[0].status_code == 409, outcomes
    with factory() as db:
        assert occupancy(db, 1) == db.get(Room, 1).current_occupancy == len(members(db, gid))
        assert len(members(db, gid)) in (1, 2)


def test_postgresql_answer_revision_races_accept(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    inv = create(client, 2)
    outcomes = race(factory,
        lambda db: invitations.transition(inv["id"], "approve", db.get(User, 2), db),
        lambda db: questionnaire.put_answers(questionnaire.Submission(answers=answers(), capacities=[4]), db.get(User, 1), db))
    assert isinstance(outcomes[1], dict), outcomes
    with factory() as db:
        outcome = db.get(Invitation, inv["id"])
        if outcome.status == "accepted":
            assert db.query(GroupMember).count() == 2
        else:
            assert outcome.status == "needs_reconfirmation" and outcome.approvals == []
            assert db.query(GroupMember).count() == 0


def test_pagination_bounded_query_and_safe_export(site):
    client, factory = site
    result = api(client, "GET", "/matches?page=2&limit=2")
    assert result["total"] == 6 and len(result["items"]) == 2
    api(client, "GET", "/matches?limit=51", expected=422)
    with factory() as db:
        db.get(Room, 1).number = '=HYPERLINK("bad")'
        db.commit()
        statements = []
        def count(*args):
            statements.append(args[2])
        event.listen(db.bind, "before_cursor_execute", count)
        try:
            assert len(MatchingContext(db, db.get(User, 1)).items()) == 6
            assert len(statements) <= 9
        finally:
            event.remove(db.bind, "before_cursor_execute", count)
    response = client.get("/admin/export?resource=rooms", headers={"X-Test-User": "9"})
    assert response.status_code == 200 and "'=HYPERLINK" in response.text
    assert "student_id" not in response.text and "answers" not in response.text


def test_idempotency_payload_conflict_and_outbox_rollback(site):
    client, factory = site
    headers = {"X-Test-User": "1", "Idempotency-Key": "one-action"}
    body = {"receiver_id": 2, "capacity": 4}
    first = client.post("/requests", json=body, headers=headers)
    assert first.status_code == 200
    api(client, "POST", f"/requests/{first.json()['id']}/approve", 2)
    assert client.post("/requests", json=body, headers=headers).json() == first.json()
    assert client.post("/requests", json={**body, "receiver_id": 3}, headers=headers).status_code == 409
    with factory() as db:
        from pilot.domain_events import notify
        before_mutation(db)
        notify(db, [1], "test", "rollback test", "group", 1, "rollback-proof")
        db.rollback()
    with factory() as db:
        assert not db.query(Notification).filter_by(event_key="rollback-proof").first()
        assert not db.query(OutboxEvent).filter_by(event_key="notice:1:rollback-proof").first()


def test_stale_allocation_retry_cannot_undo_later_move(site):
    client, factory = site
    gid = form_group(client)
    path = f"/admin/groups/{gid}/allocation"
    headers = {"X-Test-User": "9", "Idempotency-Key": "allocate-original-command"}
    body = {"room_id": 1, "reason": "تخصیص نخست"}
    first = client.post(path, headers=headers, json=body)
    assert first.status_code == 200
    api(client, "POST", path, 9, {"room_id": 2, "reason": "انتقال بعدی"})
    assert client.post(path, headers=headers, json=body).json() == first.json()
    with factory() as db:
        assert db.query(RoomAssignment).filter_by(group_id=gid).one().room_id == 2
        assert occupancy(db, 1) == 0 and occupancy(db, 2) == 2


def test_terminal_invitation_does_not_expose_later_group_members(site):
    client, _ = site
    form_group(client)
    former = create(client, 3)
    api(client, "POST", f"/requests/{former['id']}/reject", 3)
    new_member = create(client, 4)
    api(client, "POST", f"/requests/{new_member['id']}/approve", 2)
    api(client, "POST", f"/requests/{new_member['id']}/approve", 4)
    old = next(x for x in api(client, "GET", "/requests", 3)["items"] if x["id"] == former["id"])
    assert [u["id"] for u in old["group"]["members"]] == [1, 2]


def test_preflight_reports_legacy_sharing_without_evicting(site):
    client, factory = site
    g1, g2 = form_group(client), form_group(client, 3, 4)
    with factory() as db:
        db.add_all([RoomAssignment(group_id=g1, room_id=1), RoomAssignment(group_id=g2, room_id=1)])
        db.get(Room, 1).reconciliation_required = True
        db.get(Room, 1).current_occupancy = 3  # Deliberate legacy cache mismatch.
        db.commit()
        result = report(db.connection())
        assert {x["code"] for x in result["findings"]} >= {"shared_room", "room_occupancy_mismatch", "room_policy_review"}
        assert db.query(GroupMember).count() == 4 and db.query(RoomAssignment).count() == 2
        assert db.get(Room, 1).current_occupancy == 3
    api(client, "POST", f"/admin/groups/{g2}/allocation", 9, {"room_id": 2, "reason": "رفع تخصیص مشترک قدیمی"})
    with factory() as db:
        assert occupancy(db, 1) == db.get(Room, 1).current_occupancy == 2
        assert occupancy(db, 2) == db.get(Room, 2).current_occupancy == 2
        assert db.query(GroupMember).count() == 4


def test_postgresql_capacity_policy_races_allocation(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    gid = form_group(client)
    request = SimpleNamespace(state=SimpleNamespace(request_id="room-policy-race"), headers={})
    policy = housing.RoomInput(number="1", dormitory="پایلوت", capacity=2, pool="male", cycle="pilot-2026", reason="ویرایش سیاست اتاق")
    outcomes = race(factory,
        lambda db: housing.edit_room(1, policy, request, db.get(User, 9), db),
        lambda db: housing.allocate(gid, housing.Allocation(room_id=1, reason="تخصیص هم‌زمان"), request, db.get(User, 9), db))
    assert sum(isinstance(x, dict) for x in outcomes) == 1, outcomes
    assert any(isinstance(x, HTTPException) and x.status_code == 409 for x in outcomes), outcomes
    with factory() as db:
        room = db.get(Room, 1)
        assert room.current_occupancy == occupancy(db, 1) <= room.capacity
        assert (room.capacity, room.current_occupancy) in {(2, 0), (4, 2)}


def test_postgresql_concurrent_moves_preserve_all_room_counters(site):
    client, factory = site
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Race evidence requires PostgreSQL")
    gid = form_group(client)
    api(client, "POST", f"/admin/groups/{gid}/allocation", 9, {"room_id": 1, "reason": "تخصیص اولیه"})
    with factory() as db:
        db.add(Room(id=5, number="5", dormitory="پایلوت", capacity=4, pool="male", cycle="pilot-2026", reconciliation_required=False))
        db.commit()
    request = SimpleNamespace(state=SimpleNamespace(request_id="two-moves-race"), headers={})
    outcomes = race(factory, *[
        lambda db, room_id=rid: housing.allocate(gid, housing.Allocation(room_id=room_id, reason="انتقال هم‌زمان"), request, db.get(User, 9), db)
        for rid in (2, 5)])
    assert all(isinstance(x, dict) for x in outcomes), outcomes
    with factory() as db:
        current_room = db.query(RoomAssignment).filter_by(group_id=gid).one().room_id
        assert current_room in (2, 5)
        for rid in (1, 2, 5):
            assert db.get(Room, rid).current_occupancy == occupancy(db, rid) == (2 if rid == current_room else 0)
