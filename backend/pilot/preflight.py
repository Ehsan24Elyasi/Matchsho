"""Read-only invariant report, safe to run before or after the pilot migration."""
import argparse
import json
from pathlib import Path

from sqlalchemy import inspect, text

from database import engine


def report(connection):
    schema = inspect(connection)
    tables = set(schema.get_table_names())
    findings = []

    def collect(code, query, remedy):
        for row in connection.execute(text(query)).mappings():
            findings.append({"code": code, "record": dict(row), "remedy": remedy})

    if not {"users", "groups", "rooms", "group_members", "room_assignments"} <= tables:
        return {"ok": False, "findings": [{"code": "schema_missing", "remedy": "Run the migration on an approved empty database."}]}
    collect("duplicate_membership", "SELECT user_id, COUNT(*) AS count FROM group_members GROUP BY user_id HAVING COUNT(*) > 1",
            "Review each membership with the student; no automatic eviction is permitted.")
    collect("multiple_group_assignment", "SELECT group_id, COUNT(*) AS count FROM room_assignments GROUP BY group_id HAVING COUNT(*) > 1",
            "Review assignments and record a controlled move/unassignment.")
    collect("shared_room", "SELECT room_id, COUNT(*) AS groups FROM room_assignments GROUP BY room_id HAVING COUNT(*) > 1",
            "Preserve occupants; move groups through the audited operator workflow.")
    collect("group_overcapacity", "SELECT g.id, g.capacity, COUNT(gm.id) AS actual FROM groups g JOIN group_members gm ON gm.group_id=g.id GROUP BY g.id,g.capacity HAVING COUNT(gm.id)>g.capacity",
            "Review individual departures; do not silently change agreed capacity.")
    collect("room_occupancy_mismatch", "SELECT r.id, r.capacity, r.current_occupancy, COUNT(gm.id) AS actual FROM rooms r LEFT JOIN room_assignments ra ON ra.room_id=r.id LEFT JOIN group_members gm ON gm.group_id=ra.group_id GROUP BY r.id,r.capacity,r.current_occupancy HAVING COUNT(gm.id)<>r.current_occupancy OR COUNT(gm.id)>r.capacity",
            "Review memberships; reconcile the room cache using the audited room policy operation.")
    room_columns = {c["name"] for c in schema.get_columns("rooms")}
    if "pool" in room_columns:
        collect("room_policy_review", "SELECT id FROM rooms WHERE pool IS NULL OR cycle IS NULL OR reconciliation_required = true",
                "Assign an explicit reviewed pool/cycle and resolve legacy conflicts.")
        collect("group_policy_review", "SELECT id FROM groups WHERE pool IS NULL OR cycle IS NULL OR reconciliation_required = true",
                "Use the group reconciliation action after reviewing each enrollment.")
    else:
        findings.append({"code": "legacy_schema", "remedy": "Run the additive pilot migration; existing allocations will be preserved."})
    if "pilot_enrollments" in tables:
        collect("missing_roster", "SELECT u.id FROM users u LEFT JOIN pilot_enrollments e ON e.user_id=u.id WHERE u.role='user' AND u.account_status='active' AND e.id IS NULL",
                "Import the approved roster and let the email owner claim; do not infer eligibility.")
        collect("allocation_pool_mismatch", "SELECT gm.user_id, ra.room_id FROM group_members gm JOIN room_assignments ra ON ra.group_id=gm.group_id JOIN rooms r ON r.id=ra.room_id LEFT JOIN pilot_enrollments e ON e.user_id=gm.user_id WHERE e.id IS NULL OR e.pool<>r.pool OR e.cycle<>r.cycle",
                "Review roster correction or a controlled move, preserving occupied places meanwhile.")
    return {"ok": not findings, "read_only": True, "findings": findings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION READ ONLY"))
        result = report(connection)
    value = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(value, encoding="utf-8")
    print(value)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
