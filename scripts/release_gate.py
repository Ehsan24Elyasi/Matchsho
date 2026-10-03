"""Fail closed when release evidence, audit coverage or immutable image identity is absent."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = {"ci", "security_privacy", "postgres_concurrency", "migration_rollback", "browser",
            "dependency_scan", "secret_scan", "container_scan", "load", "production_tls_cookies",
            "database_tls", "real_smtp", "restore_drill", "working_alerts", "roster_and_policy",
            "operator_walkthrough", "support_and_retention"}


def errors(record: dict, directory: Path) -> list[str]:
    result = []
    for key in ("source_revision", "operator", "institution", "cycle", "support_contact", "start_at", "rollback_image"):
        if not record.get(key):
            result.append(f"Missing {key}")
    for key in ("backend_image", "frontend_image", "rollback_image"):
        if not re.fullmatch(r".+@sha256:[a-f0-9]{64}", record.get(key, "")):
            result.append(f"{key} must be an immutable digest")
    if not 1 <= record.get("cohort_size", 0) <= 50:
        result.append("Pilot cohort_size must be between 1 and 50")
    evidence = record.get("evidence", {})
    for key in sorted(REQUIRED):
        item = evidence.get(key, {})
        if item.get("status") != "passed" or not item.get("verified_at") or not item.get("owner"):
            result.append(f"Pending evidence: {key}")
        path = item.get("path")
        if not path or not (directory / path).is_file():
            result.append(f"Evidence file missing: {key}")
    audits = {item.get("id"): item for item in record.get("audit_findings", [])}
    for number in range(1, 31):
        row = audits.get(number, {})
        if row.get("status") != "verified" or not row.get("test") or not row.get("implementation"):
            result.append(f"Audit finding {number} lacks implementation/test evidence")
    if record.get("unresolved_release_blockers"):
        result.append("Unresolved release blockers")
    if record.get("authorization") != "approved-by-designated-operator":
        result.append("Designated operator has not approved admission")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8-sig"))
    problems = errors(record, args.record.resolve().parent)
    print(json.dumps({"release_ready": not problems, "problems": problems}, indent=2))
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
