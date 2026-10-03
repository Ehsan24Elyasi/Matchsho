"""Pilot cutover regressions replacing incompatible open-registration/v1 contracts.

The full domain/security workflows now live in test_pilot_domain/security. These
checks keep the public composition, migration preservation and readiness honest.
"""
import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

import main
from alembic import command
from database import validate_database_url


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_database(request, tmp_path):
    if request.param == "postgresql":
        url = os.getenv("TEST_DATABASE_URL")
        if not url:
            pytest.skip("Real PostgreSQL migration evidence requires TEST_DATABASE_URL")
        assert make_url(url).database.endswith("_test")
        schema = "test_migration_" + uuid.uuid4().hex
        control = create_engine(url)
        with control.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'migration-only.sqlite3'}")
    yield engine
    engine.dispose()
    if request.param == "postgresql":
        with control.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def alembic_config(connection):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.attributes["connection"] = connection
    return config


def test_additive_migration_preserves_legacy_places(migration_database, monkeypatch):
    engine = migration_database
    with engine.begin() as c:
        config = alembic_config(c)
        command.upgrade(config, "0001_initial")
        for uid in (1, 2, 3):
            c.execute(text("INSERT INTO users (id,email,password_hash,name,class_name,student_id,gender,role,is_active,email_verified,created_at,updated_at) VALUES (:id,:email,'legacy-hash','Legacy','CS',:sid,'male','user',true,true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                      {"id": uid, "email": f"old{uid}@example.org", "sid": f"legacy{uid}"})
        c.execute(text("INSERT INTO rooms (id,number,dormitory,capacity,current_occupancy,created_at) VALUES (1,'101','A',4,2,CURRENT_TIMESTAMP)"))
        c.execute(text("INSERT INTO groups (id,capacity,is_complete,created_at) VALUES (1,4,false,CURRENT_TIMESTAMP)"))
        c.execute(text("INSERT INTO group_members (group_id,user_id,joined_at) VALUES (1,1,CURRENT_TIMESTAMP),(1,2,CURRENT_TIMESTAMP)"))
        c.execute(text("INSERT INTO room_assignments (group_id,room_id,assigned_at) VALUES (1,1,CURRENT_TIMESTAMP)"))
        c.execute(text("INSERT INTO roommate_requests (sender_id,receiver_id,status,active_pair_key,created_at,updated_at) VALUES (1,3,'pending','1:3',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        command.upgrade(config, "head")
        assert c.scalar(text("SELECT COUNT(*) FROM group_members")) == 2
        assert c.scalar(text("SELECT COUNT(*) FROM room_assignments")) == 1
        assert c.scalar(text("SELECT current_occupancy FROM rooms WHERE id=1")) == 2
        assert c.scalar(text("SELECT reconciliation_required FROM rooms WHERE id=1"))
        assert c.scalar(text("SELECT reason FROM roommate_requests")) == "policy_upgrade"
        assert c.scalar(text("SELECT status FROM roommate_requests")) == "cancelled"
        assert c.scalar(text("SELECT COUNT(*) FROM pilot_notifications")) == 2
        assert c.scalar(text("SELECT COUNT(*) FROM pilot_allocation_history")) == 2
        assert c.scalar(text("SELECT COUNT(*) FROM pilot_questionnaires")) == 0
        assert not c.scalar(text("SELECT email_verified FROM users WHERE id=1"))
        command.check(config)
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        assert client.get("/health/ready").status_code == 200
        with engine.begin() as c:
            c.execute(text("ALTER TABLE pilot_sessions DROP COLUMN device"))
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_empty_migration_schema_drift(migration_database):
    with migration_database.begin() as c:
        config = alembic_config(c)
        command.upgrade(config, "head")
        command.check(config)
        assert "pilot_outbox" in inspect(c).get_table_names()


def test_old_unsafe_contracts_are_not_mounted():
    with TestClient(main.app) as client:
        for path, method in [("/users/1", "GET"), ("/answers/2", "PUT"), ("/rooms/1/unassign", "DELETE"),
                             ("/requests/1/accept?current_user_id=2", "PUT"), ("/match/1/2", "GET")]:
            response = client.request(method, path)
            assert response.status_code in (404, 405)
        assert client.get("/auth/me").status_code == 401
        assert client.get("/admin/rooms").status_code == 401
        assert client.get("/health/live").headers["Cache-Control"] == "no-store"
        assert client.post("/requests", headers={"X-Matchsho-Protocol": "future-incompatible"}).json()["code"] == "client_version"
        assert client.get("/pilot/config", headers={"X-Matchsho-Protocol": "3"}).status_code == 200


def test_validation_never_echoes_password_or_token():
    with TestClient(main.app) as client:
        csrf = client.get("/auth/csrf").json()["csrf_token"]
        password, token = "Secret-7", "private-token-" * 30
        result = client.post("/auth/activate", headers={"X-CSRF-Token": csrf}, json={"password": password, "token": token})
        assert result.status_code == 422
        assert password not in result.text and token not in result.text
        assert all("input" not in error and "ctx" not in error for error in result.json()["detail"])


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-ca"])
def test_effective_database_url_rejects_tls_bypass(mode, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("fixture-path-only")
    with pytest.raises(RuntimeError):
        validate_database_url(f"postgresql://fixture@db/pilot?sslmode={mode}&sslrootcert={ca.as_posix()}", "production")
    with pytest.raises(RuntimeError):
        validate_database_url("postgresql://fixture@db/pilot?sslmode=verify-full", "production")
