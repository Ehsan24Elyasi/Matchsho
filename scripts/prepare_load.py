"""Provision exactly 50 synthetic users by roster, outbox/Mailpit and activation APIs."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ops_common import now, write_report
from stack_smoke import Browser


def write_snapshot_command(compose: list[str], fixture_id: str) -> list[str]:
    if not re.fullmatch(r"load-[a-f0-9]{8}", fixture_id):
        raise ValueError("Invalid synthetic fixture identifier")
    query = f"""SELECT json_build_object(
      'table_updates', (SELECT n_tup_upd FROM pg_stat_user_tables WHERE schemaname='public' AND relname='pilot_questionnaires'),
      'rows', (SELECT json_agg(row_to_json(r) ORDER BY r.index) FROM (
        SELECT split_part(split_part(u.email,'@',1),'-',3)::int AS index,
          q.updated_at::text AS updated_at,
          encode(sha256(convert_to(q.draft::text,'UTF8')),'hex') AS draft_hash,
          encode(sha256(convert_to(q.answers::text,'UTF8')),'hex') AS published_hash,
          q.draft -> 'answers' -> 'sleep' ->> 'own' AS draft_sleep
        FROM pilot_questionnaires q JOIN users u ON u.id=q.user_id
        WHERE u.email LIKE '{fixture_id}-%@example.com'
      ) r))"""
    return compose + ["exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "postgres",
                      "psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set", "ON_ERROR_STOP=1",
                      "-U", "matchsho", "-d", "matchsho", "--command", query]

ANSWERS = {
    "sleep": {"own": "23:00", "accepted": ["22:00", "01:00"], "importance": 2, "hard": False},
    "wake": {"own": "07:00", "accepted": ["06:00", "09:00"], "importance": 2, "hard": False},
    "cleaning": {"own": "weekly", "accepted": ["weekly", "daily"], "importance": 2, "hard": False},
    "guests": {"own": "never", "accepted": ["never"], "importance": 2, "hard": False},
    "noise": {"own": "quiet", "accepted": ["quiet"], "importance": 2, "hard": False},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8088")
    parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", default="matchsho-pilot-test")
    args = parser.parse_args()
    if not args.origin.startswith(("http://localhost:", "http://127.0.0.1:")) or not args.env_file.name.startswith(".env.pilot-"):
        parser.error("Only an explicitly isolated local test stack is allowed.")
    if args.output.exists() or not args.project.endswith(("-test", "-ci")):
        parser.error("Use a new private fixture output and a -test/-ci Compose project.")
    values = dict(line.split("=", 1) for line in args.env_file.read_text(encoding="utf-8-sig").splitlines()
                  if line and not line.startswith("#") and "=" in line)
    admin = Browser(args.origin)
    admin.prepare()
    assert admin.call("/api/auth/login", {"email": values["ADMIN_EMAIL"], "password": values["ADMIN_PASSWORD"]})[0] == 200
    suffix = secrets.token_hex(4)
    fixture_id = "load-" + suffix
    rows = [{"student_id": f"{fixture_id}-{i}", "email": f"{fixture_id}-{i}@example.com", "name": f"دانشجوی آزمون {i}",
             "class_name": "آزمون بار", "gender": "male", "pool": "male", "cycle": "pilot-2026"} for i in range(50)]
    assert admin.call("/api/admin/roster/import", {"rows": rows, "dry_run": True, "reason": "Synthetic load fixture"})[0] == 200
    assert admin.call("/api/admin/roster/import", {"rows": rows, "dry_run": False, "reason": "Synthetic load fixture"})[0] == 200
    assert admin.call("/api/admin/rooms", {"number": fixture_id, "dormitory": "آزمون بار", "capacity": 2,
                                         "pool": "male", "cycle": "pilot-2026", "reason": "Synthetic performance fixture"})[0] in {200, 201}
    users = []
    for index, row in enumerate(rows):
        client = Browser(args.origin)
        client.prepare()
        password = secrets.token_urlsafe(24)
        if admin.call("/api/pilot/config")[1].get("email_verification_required"):
            status, _, _ = client.call("/api/auth/register", {"student_id": row["student_id"]})
            assert status == 202, f"Fixture claim {index} failed with {status}; do not weaken the limiter"
            deadline, token = time.monotonic() + 35, None
            while time.monotonic() < deadline:
                with urllib.request.urlopen(args.mailpit + "/api/v1/messages?limit=200", timeout=10) as response:
                    messages = json.load(response)
                message = next((m for m in messages.get("messages", []) if any(t.get("Address") == row["email"] for t in m.get("To", []))), None)
                if message:
                    with urllib.request.urlopen(args.mailpit + "/api/v1/message/" + message["ID"], timeout=10) as response:
                        body = json.load(response).get("Text", "")
                    if "token=" in body:
                        token = urllib.parse.unquote(body.split("token=", 1)[1].split()[0])
                        break
                time.sleep(.4)
            assert token, f"Fixture message {index} failed to reach the local test sink"
            assert client.call("/api/auth/activate", {"token": token, "password": password})[0] == 200
        else:
            registration = {key: row[key] for key in ("student_id", "email", "name", "class_name", "gender")}
            assert client.call("/api/auth/register", {**registration, "password": password})[0] == 201
        assert client.call("/api/me/consent", {"discovery": True, "explanations": False}, "PATCH")[0] == 200
        assert client.call("/api/questionnaire/me", {"version": 2, "answers": ANSWERS, "capacities": [2]}, "PUT")[0] == 200
        users.append({"email": row["email"], "password": password})
        print(f"Activated fixture account {index + 1}/50", flush=True)
    info = subprocess.run(["docker", "info", "--format", "{{json .}}"], capture_output=True, text=True, check=True)
    machine = json.loads(info.stdout)
    compose = ["docker", "compose", "--env-file", str(args.env_file.resolve()), "-p", args.project]
    fixture = {"fixture_id": fixture_id, "created_at": now(), "disposable": True, "origin": args.origin, "users": users,
               "expected_conflicts": [],
               "draft_sleep_times": ["23:15", "23:00"],
               "write_snapshot_command": write_snapshot_command(compose, fixture_id),
               "reads": [{"path": "/matches?limit=12"}, {"path": "/matches?limit=12"}, {"path": "/notifications?limit=20"},
                         {"path": "/requests?limit=20"}],
               "writes": [{"path": "/questionnaire/draft", "method": "PUT", "body": {"version": 2, "answers": ANSWERS, "capacities": [2]}}],
               "invariant_command": compose + ["exec", "-T", "matchsho-backend", "python", "-m", "pilot.preflight"],
               "machine": {"docker_cpus": machine.get("NCPU"), "docker_memory_bytes": machine.get("MemTotal"),
                           "os": machine.get("OperatingSystem"), "runtime": "Python3.11/PostgreSQL16, local Docker Desktop"},
               "database_size": {"fixture_students": 50, "complete_questionnaires": 50, "synthetic_prior_e2e_data": True},
               "rate_limit_configuration": {"login_account_15m": 20, "login_ip_15m": 200, "claim_ip_hour": 60,
                                            "email_ip_hour": 60, "argon2_concurrency": 2, "hashing": "Argon2 defaults unchanged"}}
    write_report(args.output, fixture)
    os.chmod(args.output, 0o600)
    print(json.dumps({"fixture_id": fixture_id, "private_fixture": str(args.output), "users": 50}))


if __name__ == "__main__":
    main()
