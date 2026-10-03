"""Check published readiness, authorized mail health and backup age; notify on changes."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from ops_common import now, write_report


def evaluate(delivery: dict, backup: dict, ready: bool, moment: datetime | None = None) -> list[str]:
    moment = moment or datetime.now(UTC)
    alerts = []
    if not ready:
        alerts.append("api-readiness-loss")
    heartbeat = delivery.get("last_heartbeat_at")
    try:
        last = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        heartbeat_age = (moment - last).total_seconds()
    except (AttributeError, ValueError, TypeError):
        heartbeat_age = float("inf")
    if heartbeat_age > 120:
        alerts.append("worker-heartbeat-loss")
    if delivery.get("oldest_pending_age_seconds", 0) > 300:
        alerts.append("mail-pending-over-five-minutes")
    if delivery.get("terminal_failures", 0) > 0:
        alerts.append("mail-terminal-failure")
    try:
        finished = datetime.fromisoformat(backup["finished_at"])
        fresh = 0 <= (moment - finished).total_seconds() <= 86400
    except (KeyError, ValueError, TypeError):
        fresh = False
    if backup.get("status") != "passed" or not fresh:
        alerts.append("backup-failure-or-overdue")
    return sorted(alerts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--backup-report", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.origin.startswith("https://") and not args.origin.startswith("http://localhost:"):
        parser.error("Use HTTPS, or localhost for an isolated drill.")
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def fetch(path: str, data: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        csrf = next((cookie.value for cookie in cookies if cookie.name == "csrf_token"), None)
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(args.origin.rstrip("/") + path,
                                         data=json.dumps(data).encode() if data is not None else None,
                                         headers=headers)
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    ready, delivery = False, {}
    try:
        fetch("/api/health/ready")
        ready = True
        fetch("/api/auth/csrf")
        fetch("/api/auth/login", {"email": os.environ["OPS_EMAIL"], "password": os.environ["OPS_PASSWORD"]})
        delivery = fetch("/api/admin/delivery/health")
    except (urllib.error.URLError, KeyError, ValueError):
        pass
    try:
        backup = json.loads(args.backup_report.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        backup = {}
    alerts = evaluate(delivery, backup, ready)
    try:
        old = json.loads(args.state.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        old = {}
    report = {"checked_at": now(), "alerts": alerts, "status": "alert" if alerts else "healthy"}
    changed = old.get("alerts") != alerts
    # Write state only after successful delivery so a failed webhook is retried.
    webhook = os.environ.get("OPS_ALERT_WEBHOOK", "")
    if changed and not args.dry_run:
        if not webhook.startswith("https://"):
            raise SystemExit("Set an HTTPS OPS_ALERT_WEBHOOK; no notification was sent and state is unchanged.")
        payload = json.dumps({"service": "matchsho", "time": now(), "alerts": alerts,
                              "recovered": not alerts, "runbook": "docs/pilot/operations.md"}).encode()
        request = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 300:
                    raise SystemExit("Alert delivery failed; state unchanged.")
        except urllib.error.URLError:
            raise SystemExit("Alert delivery failed; state unchanged.") from None
    if not args.dry_run:
        write_report(args.state, report)
    print(json.dumps({**report, "changed": changed, "notification_sent": changed and not args.dry_run}))
    raise SystemExit(1 if alerts else 0)


if __name__ == "__main__":
    main()
