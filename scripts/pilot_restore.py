"""Restore into a guarded, empty quarantine DB; replay current erasures and run smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from ops_common import (
    OpsError,
    database_env,
    database_identity,
    now,
    run,
    sql,
    write_report,
)


def validate_target(source: tuple, target: tuple, confirmation: str, outbound_disabled: bool) -> None:
    if source == target:
        raise OpsError("Restore target must differ from the live source database.")
    if not target[2].startswith("matchsho_restore_") or target[2] != confirmation:
        raise OpsError("Target must be named matchsho_restore_<drill> and explicitly confirmed.")
    if not outbound_disabled:
        raise OpsError("Set NO_OUTBOUND_EMAIL=true before starting a restore.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True, help="Downloaded encrypted .dump.age")
    parser.add_argument("--backup-report", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True, help="Protected age private-key file")
    parser.add_argument("--ledger", type=Path, required=True, help="Fresh erasure ledger exported AFTER this backup")
    parser.add_argument("--confirm-target", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=Path(__file__).resolve().parents[1] / "backend")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--smoke", nargs=argparse.REMAINDER, required=True,
                        help="Isolated student/operator smoke command; no shell evaluation")
    args = parser.parse_args()
    started = monotonic()
    report = {"kind": "restore-drill", "started_at": now(), "status": "failed", "outbound_email_disabled": True,
              "rpo_seconds": 86400, "rto_seconds": 14400, "checks": []}
    try:
        if not args.smoke:
            raise OpsError("Student/operator smoke command is required; restore alone cannot pass.")
        source_env, source = database_env(os.environ.get("SOURCE_DATABASE_URL", ""), development=args.development)
        target_raw = os.environ.get("RESTORE_DATABASE_URL", "")
        target_env, target = database_env(target_raw, development=args.development)
        validate_target(source, target, args.confirm_target, os.environ.get("NO_OUTBOUND_EMAIL", "").lower() == "true")
        source_identity = database_identity(source_env)
        target_identity = database_identity(target_env)
        if source_identity == target_identity:
            raise OpsError("Live and restore database identities match (hostname aliases are unsafe).")
        report["target_identity"] = target_identity
        if sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'", target_env) != "0":
            raise OpsError("Restore target is not empty; this command never clears existing data.")
        if sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()", target_env) != "0":
            raise OpsError("Restore target has active clients; stop all app/worker processes first.")
        backup_report = json.loads(args.backup_report.read_text(encoding="utf-8-sig"))
        if backup_report.get("status") != "passed" or not backup_report.get("offhost_verified"):
            raise OpsError("A verified off-host backup report is required.")
        if backup_report.get("source_identity") != source_identity:
            raise OpsError("Backup source identity does not match the nominated live source.")
        backup_time = datetime.fromisoformat(backup_report["started_at"])
        age_seconds = (datetime.now(UTC) - backup_time).total_seconds()
        report["backup_age_seconds"] = round(age_seconds)
        if not 0 <= age_seconds <= 86400:
            raise OpsError("Backup age violates the 24-hour recovery point objective.")
        if hashlib.sha256(args.backup.read_bytes()).hexdigest() != backup_report.get("ciphertext_sha256"):
            raise OpsError("Encrypted backup digest does not match its evidence report.")
        ledger = json.loads(args.ledger.read_text(encoding="utf-8-sig"))
        ledger_path = args.ledger.resolve()
        exported_at = datetime.fromisoformat(ledger["exported_at"])
        if exported_at < backup_time or (datetime.now(UTC) - exported_at).total_seconds() > 3600:
            raise OpsError("Export a current erasure ledger from live storage within the last hour.")
        report["ledger_sha256"] = hashlib.sha256(args.ledger.read_bytes()).hexdigest()
        report["checks"].append("separate-empty-target-and-fresh-ledger")
        with tempfile.TemporaryFile() as age_errors, tempfile.TemporaryFile() as restore_errors:
            decrypt = subprocess.Popen(["age", "--decrypt", "--identity", str(args.identity), str(args.backup)],
                                       stdout=subprocess.PIPE, stderr=age_errors)
            try:
                restore = subprocess.Popen(["pg_restore", "--no-owner", "--no-acl", "--exit-on-error",
                                            "--single-transaction", "--dbname", target[2]],
                                           stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
                                           stderr=restore_errors, env=target_env)
                decrypt.stdout.close()
                restore_code = restore.wait(timeout=10800)
                decrypt_code = decrypt.wait(timeout=30)
            except BaseException:
                decrypt.kill()
                decrypt.wait()
                if "restore" in locals() and restore.poll() is None:
                    restore.kill()
                    restore.wait()
                raise
            if restore_code or decrypt_code:
                raise OpsError("Decryption or restore failed; quarantine database must remain closed.")
        report["checks"].append("age-authentication-and-atomic-restore")
        app_env = os.environ.copy()
        app_env.update(DATABASE_URL=target_raw, ENVIRONMENT="test", AUTO_CREATE_DB="false",
                       NO_OUTBOUND_EMAIL="true", SMTP_HOST="127.0.0.1", SMTP_PORT="1")
        # Relative module execution in the release backend; never automatically downgrade.
        original = Path.cwd()
        try:
            os.chdir(args.backend.resolve())
            run([sys.executable, "-m", "pilot.migrate"], env=app_env, timeout=1800)
            run([sys.executable, "-m", "pilot.maintenance", "--reapply-erasure", "--ledger", str(ledger_path)],
                env=app_env, timeout=1800)
            run([sys.executable, "-m", "pilot.preflight"], env=app_env, timeout=120)
        finally:
            os.chdir(original)
        report["checks"].extend(["supported-schema", "current-erasure-ledger-reapplied", "domain-invariants"])
        run(args.smoke, env=app_env, timeout=1800)
        report["checks"].append("isolated-student-and-operator-smoke")
        if monotonic() - started > 14400:
            raise OpsError("Restore and validation exceeded the four-hour recovery time objective.")
        report["status"] = "passed"
    except (OpsError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error) if isinstance(error, OpsError) else type(error).__name__
    finally:
        report.update(finished_at=now(), duration_seconds=round(monotonic() - started, 2))
        write_report(args.report, report)
    print(json.dumps({"status": report["status"], "report": str(args.report),
                      "quarantined": True, "live_traffic_authorized": False}))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
