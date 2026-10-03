from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops_common import OpsError, database_env, remote_guard
from pilot_alerts import evaluate
from pilot_restore import validate_target


class RestoreGuardTests(unittest.TestCase):
    def test_rejects_source_database(self):
        identity = ("db.example.edu", 5432, "matchsho")
        with self.assertRaises(OpsError):
            validate_target(identity, identity, "matchsho", True)

    def test_rejects_target_without_required_prefix(self):
        with self.assertRaises(OpsError):
            validate_target(("db", 5432, "source"), ("db", 5432, "production"), "production", True)

    def test_requires_exact_confirmation_and_disabled_outbound(self):
        target = ("db", 5432, "matchsho_restore_drill")
        for confirmation, disabled in [("wrong", True), (target[2], False)]:
            with self.subTest(confirmation=confirmation, disabled=disabled), self.assertRaises(OpsError):
                validate_target(("db", 5432, "source"), target, confirmation, disabled)

    def test_accepts_explicit_distinct_quarantined_target(self):
        validate_target(("db", 5432, "source"), ("db", 5432, "matchsho_restore_test"), "matchsho_restore_test", True)


class DatabaseGuardTests(unittest.TestCase):
    def test_production_requires_hostname_and_ca_verification(self):
        for mode in ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]:
            with self.subTest(mode=mode), self.assertRaises(OpsError):
                database_env(f"postgresql://user:fixture-password@db.example.edu/matchsho?sslmode={mode}")

    def test_no_credentials_in_arguments(self):
        env, identity = database_env("postgresql://u:p%40ss@db.example.edu/matchsho?sslmode=verify-full&sslrootcert=/ca.pem")
        self.assertEqual(env["PGPASSWORD"], "p@ss")
        self.assertEqual(identity, ("db.example.edu", 5432, "matchsho"))
        self.assertNotIn("p@ss", str(identity))

    def test_local_exception_does_not_allow_remote_hosts(self):
        with self.assertRaises(OpsError):
            database_env("postgresql://u:p@external.example.edu/db?sslmode=disable", development=True)
        env, _ = database_env("postgresql://u:p@127.0.0.1/db?sslmode=disable", development=True)
        self.assertEqual(env["PGSSLMODE"], "disable")

    def test_ambiguous_ssl_options_rejected(self):
        with self.assertRaises(OpsError):
            database_env("postgresql://u:p@db.example.edu/db?sslmode=verify-full&sslmode=disable&sslrootcert=/ca")


class BackupGuardTests(unittest.TestCase):
    def test_refuses_local_and_remote_root_destinations(self):
        for target in ["C:\\backups", "/backup", "remote:", "remote:/", "remote:matchsho-backups"]:
            with self.subTest(target=target), self.assertRaises(OpsError):
                remote_guard(target, {"remote": {"type": "s3"}})
        with self.assertRaises(OpsError):
            remote_guard("local:site/matchsho-backups", {"local": {"type": "local"}})

    def test_refuses_traversal(self):
        with self.assertRaises(OpsError):
            remote_guard("remote:site/../matchsho-backups", {"remote": {"type": "s3"}})

    def test_accepts_explicit_offhost_prefix(self):
        remote_guard("remote:university/matchsho-backups", {"remote": {"type": "s3"}})


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 2, 10, tzinfo=UTC)
        self.delivery = {"last_heartbeat_at": self.now.isoformat(), "oldest_pending_age_seconds": 0, "terminal_failures": 0}
        self.backup = {"status": "passed", "finished_at": self.now.isoformat()}

    def test_healthy_stack(self):
        self.assertEqual(evaluate(self.delivery, self.backup, True, self.now), [])

    def test_worker_mail_and_backup_alerts(self):
        self.delivery.update(last_heartbeat_at=(self.now - timedelta(minutes=3)).isoformat(),
                             oldest_pending_age_seconds=301, terminal_failures=1)
        self.backup["finished_at"] = (self.now - timedelta(hours=25)).isoformat()
        self.assertEqual(evaluate(self.delivery, self.backup, False, self.now),
                         ["api-readiness-loss", "backup-failure-or-overdue", "mail-pending-over-five-minutes",
                          "mail-terminal-failure", "worker-heartbeat-loss"])

    def test_missing_records_fail_closed(self):
        self.assertEqual(evaluate({}, {}, True, self.now), ["backup-failure-or-overdue", "worker-heartbeat-loss"])


if __name__ == "__main__":
    unittest.main()
