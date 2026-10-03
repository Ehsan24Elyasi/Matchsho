"""Exercise a disposable published Nginx stack and durable test-sink delivery."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ops_common import now, write_report


class Browser:
    def __init__(self, origin):
        self.origin = origin.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ""

    def call(self, path, data=None, method=None, headers=None):
        values = {"Content-Type": "application/json", **(headers or {})}
        if self.csrf:
            values["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(self.origin + path, headers=values,
                                         data=json.dumps(data).encode() if data is not None else None,
                                         method=method)
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read()
                parsed = json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body.decode()
                return response.status, parsed, dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, {}, dict(error.headers)

    def prepare(self):
        status, value, _ = self.call("/api/auth/csrf")
        assert status == 200, "CSRF through proxy failed"
        self.csrf = value["csrf_token"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8088")
    parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.origin.startswith(("http://localhost:", "http://127.0.0.1:")) or not args.env_file.name.startswith(".env.pilot-"):
        parser.error("This mutating smoke is only for an explicitly disposable local stack.")
    values = dict(line.split("=", 1) for line in args.env_file.read_text(encoding="utf-8-sig").splitlines()
                  if line and not line.startswith("#") and "=" in line)
    report = {"kind": "published-stack-smoke", "started_at": now(), "status": "failed", "checks": [],
              "external_launch_evidence": False}
    try:
        admin = Browser(args.origin)
        status, page, headers = admin.call("/")
        assert status == 200 and "no-cache" in headers.get("Cache-Control", ""), "HTML must revalidate"
        asset = re.search(r'(?:href|src)="(/assets/[^"]+\.(?:css|js))"', page)[1]
        status, _, headers = admin.call(asset)
        assert status == 200 and "immutable" in headers.get("Cache-Control", ""), "Fingerprinted assets must be immutable"
        report["checks"].append("same-origin-html-and-fingerprinted-cache")
        assert admin.call("/api/health/ready")[0] == 200, "Schema readiness failed"
        assert admin.call("/api/pilot/config", headers={"X-Matchsho-Protocol": "old"})[0] == 409, "Old clients must reload"
        report["checks"].append("incompatible-client-protocol-rejected")
        admin.prepare()
        for spoof in ("203.0.113.71", "198.51.100.94"):
            status, _, headers = admin.call("/api/auth/login", {"email": values["ADMIN_EMAIL"], "password": values["ADMIN_PASSWORD"]},
                headers={"X-Forwarded-For": spoof, "X-Real-IP": spoof, "X-Request-ID": "attacker-fixed-id",
                         "Forwarded": f"for={spoof}", "X-Forwarded-Proto": "https"})
            assert status == 200, "Operator login failed"
            assert headers.get("X-Request-ID") != "attacker-fixed-id", "Edge must overwrite request ID"
        report["checks"].append("operator-login-csrf-and-edge-request-id")
        suffix = secrets.token_hex(4)
        student_id, email = "ops" + suffix, "ops" + suffix + "@example.com"
        row = {"student_id": student_id, "email": email, "name": "آزمون عملیاتی", "class_name": "آزمایشی",
               "gender": "male", "pool": "male", "cycle": "pilot-2026"}
        assert admin.call("/api/admin/roster/import", {"rows": [row], "dry_run": True, "reason": "Synthetic stack acceptance"})[0] == 200
        assert admin.call("/api/admin/roster/import", {"rows": [row], "dry_run": False, "reason": "Synthetic stack acceptance"})[0] == 200
        student = Browser(args.origin)
        student.prepare()
        assert student.call("/api/auth/register", {"student_id": student_id})[0] == 202
        token = None
        mail_start = time.monotonic()
        while time.monotonic() - mail_start < 30:
            with urllib.request.urlopen(args.mailpit + "/api/v1/messages", timeout=5) as response:
                mail = json.load(response)
            message = next((m for m in mail.get("messages", []) if any(t.get("Address") == email for t in m.get("To", []))), None)
            if message:
                with urllib.request.urlopen(args.mailpit + "/api/v1/message/" + message["ID"], timeout=5) as response:
                    body = json.load(response).get("Text", "")
                match = re.search(r"token=([^\s&]+)", body)
                if match:
                    token = urllib.parse.unquote(match[1])
                    break
            time.sleep(.5)
        assert token, "Queued activation was not delivered by the worker to the test sink"
        report["sink_delivery_seconds"] = round(time.monotonic() - mail_start, 2)
        status, _, _ = student.call("/api/auth/activate", {"token": token, "password": secrets.token_urlsafe(20)})
        assert status == 200, "Delivered one-time activation failed"
        assert student.call("/api/auth/activate", {"token": token, "password": secrets.token_urlsafe(20)})[0] == 400
        assert student.call("/api/me/consent", {"discovery": True, "explanations": False}, "PATCH")[0] == 200
        assert student.call("/api/admin/groups")[0] == 403, "Role boundary failed"
        report["checks"].extend(["roster-preview-and-import", "durable-mailpit-delivery", "one-time-activation",
                                "same-origin-protected-mutation", "student-cannot-access-operator"])
        assert student.call("/api/auth/logout", {}, "POST")[0] == 200
        assert student.call("/api/me")[0] == 401
        _, health, _ = admin.call("/api/admin/delivery/health")
        assert health.get("last_heartbeat_at") and not health.get("alerts"), "Worker/delivery unhealthy"
        report["checks"].extend(["logout", "worker-heartbeat-and-delivery-health"])
        report["status"] = "passed"
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as error:
        report["error"] = str(error) if isinstance(error, AssertionError) else type(error).__name__
    finally:
        report["finished_at"] = now()
        write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
