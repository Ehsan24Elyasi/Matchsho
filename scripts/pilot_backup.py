"""Stream pg_dump through age, verify encrypted off-host upload, optionally prune >30d."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ops_common import (
    OpsError,
    database_env,
    database_identity,
    now,
    remote_guard,
    run,
    write_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, help="rclone remote:institution/matchsho-backups")
    parser.add_argument("--recipient", required=True, help="Public age encryption recipient; keep private key off-host")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prune-expired", action="store_true")
    parser.add_argument("--development", action="store_true", help="Only isolated local source may omit DB TLS")
    args = parser.parse_args()
    report = {"kind": "backup", "started_at": now(), "status": "failed", "retention_days": 30}
    try:
        config = json.loads(run(["rclone", "config", "dump"]))
        remote_guard(args.destination, config)
        if not args.recipient.startswith(("age1", "ssh-ed25519 ", "ssh-rsa ")):
            raise OpsError("Use an age recipient or supported SSH public key, never a passphrase.")
        env, _ = database_env(os.environ.get("SOURCE_DATABASE_URL", ""), development=args.development)
        report["source_identity"] = database_identity(env)
        report["database_version"] = run(["pg_dump", "--version"])
        name = datetime.now(UTC).strftime("matchsho-%Y%m%dT%H%M%SZ") + ".dump.age"
        with tempfile.TemporaryDirectory(prefix="matchsho-backup-") as temporary:
            encrypted = Path(temporary) / name
            # The only file written is encrypted. Dump stderr is private and never copied to reports.
            with tempfile.TemporaryFile() as dump_errors, tempfile.TemporaryFile() as age_errors:  # noqa: SIM117
                with encrypted.open("xb") as ciphertext:
                    os.chmod(encrypted, 0o600)
                    dump = subprocess.Popen(["pg_dump", "--format=custom", "--no-owner", "--no-acl"], env=env,
                                            stdout=subprocess.PIPE, stderr=dump_errors)
                    try:
                        encrypt = subprocess.Popen(["age", "--encrypt", "--recipient", args.recipient],
                                                   stdin=dump.stdout, stdout=ciphertext, stderr=age_errors)
                        dump.stdout.close()
                        encrypt_code = encrypt.wait(timeout=7200)
                        dump_code = dump.wait(timeout=30)
                    except BaseException:
                        dump.kill()
                        dump.wait()
                        if "encrypt" in locals() and encrypt.poll() is None:
                            encrypt.kill()
                            encrypt.wait()
                        raise
                    if dump_code or encrypt_code:
                        raise OpsError("Dump/encryption failed; no valid backup was uploaded.")
            digest = hashlib.sha256(encrypted.read_bytes()).hexdigest()
            remote_file = args.destination.rstrip("/") + "/" + name
            run(["rclone", "copyto", str(encrypted), remote_file], timeout=7200)
            run(["rclone", "check", temporary, args.destination, "--one-way", "--download", "--include", name], timeout=7200)
            report.update(status="passed", backup_file=name, ciphertext_sha256=digest,
                          encrypted_bytes=encrypted.stat().st_size, offhost_verified=True)
            if args.prune_expired:
                # Guarded prefix and exact app filename glob; never delete remote root.
                run(["rclone", "delete", args.destination, "--min-age", "30d", "--include", "matchsho-*.dump.age"], timeout=600)
                report["expired_backups_pruned"] = True
    except (OpsError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error) if isinstance(error, OpsError) else type(error).__name__
    finally:
        report["finished_at"] = now()
        write_report(args.report, report)
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
