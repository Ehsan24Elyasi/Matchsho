"""Repeatable 50-user, 10-minute pilot workload against an isolated published stack."""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import http.cookiejar
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ops_common import OpsError, now, run, write_report


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * percentile_value))], 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True, help="Private JSON workload: see operations.md")
    parser.add_argument("--confirm-fixture", required=True, help="Exact isolated fixture_id")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--warmup", type=int, default=30)
    args = parser.parse_args()
    fixture_bytes = args.fixture.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("fixture_id") != args.confirm_fixture or not fixture.get("disposable"):
        parser.error("Only an explicitly confirmed disposable fixture may be exercised.")
    users = fixture.get("users", [])
    if len(users) != 50 or not fixture.get("writes") or not fixture.get("reads") or not fixture.get("invariant_command"):
        parser.error("Fixture needs 50 users, reads, meaningful writes and an invariant command.")
    if not fixture.get("write_snapshot_command") or fixture.get("draft_sleep_times") != ["23:15", "23:00"]:
        parser.error("This acceptance fixture requires alternating draft sleep times and read-only database write evidence.")
    if not fixture.get("machine") or not fixture.get("database_size") or not fixture.get("rate_limit_configuration"):
        parser.error("Record machine resources, DB fixture size and limiter settings.")
    if args.seconds < 600 or args.warmup < 10:
        parser.error("Acceptance measurement must be at least 600s after at least 10s warm-up.")
    origin = fixture["origin"].rstrip("/")
    if not origin.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
        parser.error("Use HTTPS or a loopback isolated stack.")
    stats: dict[str, list] = {"read_ms": [], "write_ms": [], "matching_ms": [], "auth_ms": [], "auth_status": [], "status": []}
    endpoints: dict[str, dict[str, list]] = {}
    privacy_violations = []
    protocol_violations = []
    lock = threading.Lock()
    gate = threading.Barrier(50, timeout=180)
    started = time.monotonic()
    measurement = {"expected_final": {}}

    def snapshot() -> dict:
        return json.loads(run(fixture["write_snapshot_command"], timeout=120))

    def begin_measurement() -> None:
        # No actor issues a request while this barrier action captures the baseline.
        time.sleep(1.5)  # Let PostgreSQL publish the last warm-up backend statistics.
        measurement["before"] = snapshot()
        measurement["first_variant"] = {int(row["index"]): 1 if row["draft_sleep"] == "23:15" else 0
                                        for row in measurement["before"]["rows"]}
        report["measurement_started_at"] = now()
        measurement["begin"] = time.monotonic()

    measurement_gate = threading.Barrier(50, action=begin_measurement, timeout=180)

    def user_work(index: int, user: dict) -> None:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        rng = random.Random(20261002 + index)

        def request(action: dict) -> tuple[int, float]:
            headers = {"Content-Type": "application/json", "X-Matchsho-Protocol": "3",
                       "Idempotency-Key": f"load-{index}-{time.monotonic_ns()}"}
            csrf = next((c.value for c in jar if c.name == "csrf_token"), None)
            if csrf:
                headers["X-CSRF-Token"] = csrf
            body = json.dumps(action["body"]).encode() if "body" in action else None
            req = urllib.request.Request(origin + "/api" + action["path"], data=body,
                                         method=action.get("method", "GET"), headers=headers)
            start = time.monotonic()
            try:
                with opener.open(req, timeout=60 if action["path"] == "/auth/login" else 10) as response:
                    content = response.read()
                    status = response.status
                    if response.headers.get("X-Matchsho-Protocol") != "3":
                        with lock:
                            protocol_violations.append("incompatible-response")
                    if action["path"].startswith("/matches") and status == 200:
                        matches = json.loads(content)
                        for item in matches.get("items", []):
                            peers = [item.get("user") or {}] + (item.get("group") or {}).get("members", [])
                            if any({"email", "student_id", "answers", "password_hash"} & set(peer) for peer in peers):
                                with lock:
                                    privacy_violations.append("private-peer-field")
            except urllib.error.HTTPError as error:
                status = error.code
            except (urllib.error.URLError, TimeoutError, OSError):
                status = 599
            return status, (time.monotonic() - start) * 1000

        request({"path": "/auth/csrf"})
        status, duration = request({"path": "/auth/login", "method": "POST",
                                    "body": {"email": user["email"], "password": user["password"]}})
        with lock:
            stats["auth_ms"].append(duration)
            stats["auth_status"].append(status)
        if status != 200:
            gate.abort()
            raise OpsError("Fixture login failed; no credentials were included in the report.")
        gate.wait()
        warmup_end = time.monotonic() + args.warmup
        write_counter = 0

        def perform_action(measured: bool) -> None:
            nonlocal write_counter
            write = rng.random() < 0.20
            options = fixture["writes"] if write else fixture["reads"]
            action = copy.deepcopy(rng.choice(options))
            action["path"] = action["path"].format(**user.get("bindings", {}))
            if write:
                if action["path"] != "/questionnaire/draft" or action.get("method") != "PUT":
                    raise OpsError("This evidence workload requires draft PUT writes.")
                action["body"]["answers"]["sleep"]["own"] = fixture["draft_sleep_times"][write_counter % 2]
                write_counter += 1
            status, duration = request(action)
            if measured:
                with lock:
                    if write and 200 <= status < 300:
                        measurement["expected_final"][index] = action["body"]["answers"]["sleep"]["own"]
                    stats["write_ms" if write else "read_ms"].append(duration)
                    stats["status"].append(status)
                    path = urllib.parse.urlsplit(action["path"]).path
                    if path == "/matches":
                        stats["matching_ms"].append(duration)
                    endpoint = endpoints.setdefault(action.get("method", "GET") + " " + path, {"ms": [], "status": []})
                    endpoint["ms"].append(duration)
                    endpoint["status"].append(status)
            time.sleep(1.5 + rng.random())

        while time.monotonic() < warmup_end:
            perform_action(False)
        measurement_gate.wait()
        write_counter = measurement["first_variant"][index]
        end = measurement["begin"] + args.seconds
        while time.monotonic() < end:
            perform_action(True)

    report = {"kind": "pilot-load", "started_at": now(), "status": "failed", "users": 50,
              "measurement_seconds": args.seconds, "warmup_seconds": args.warmup,
              "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
              "fixture_id": fixture["fixture_id"], "machine": fixture["machine"],
              "database_size": fixture["database_size"], "rate_limit_configuration": fixture["rate_limit_configuration"],
              "mix": {"read": 0.8, "write": 0.2}, "smtp_latency": "Measure separately in real delivery evidence",
              "protocol": "3", "auth_timeout_seconds": 60, "ordinary_request_timeout_seconds": 10}
    report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["write_variation"] = "Each actor alternates private draft sleep.own between23:15 and23:00; deep copy per request; published answers unchanged."
    report["think_time_seconds"] = {"min": 1.5, "max": 2.5}
    try:
        run(fixture["invariant_command"], timeout=120)
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
            list(pool.map(lambda item: user_work(*item), enumerate(users)))
        report["measurement_finished_at"] = now()
        successful_writes = sum(200 <= status < 300 for status in endpoints.get("PUT /questionnaire/draft", {}).get("status", []))
        time.sleep(1.5)
        after = snapshot()
        before = measurement["before"]
        # Stats are asynchronously flushed; retries are outside the measured window.
        for _ in range(4):
            if after["table_updates"] - before["table_updates"] >= successful_writes:
                break
            time.sleep(1)
            after = snapshot()
        previous = {int(row["index"]): row for row in before["rows"]}
        current = {int(row["index"]): row for row in after["rows"]}
        advanced = sum(current[index]["updated_at"] > row["updated_at"] for index, row in previous.items() if index in current)
        published_unchanged = sum(current[index]["published_hash"] == row["published_hash"] for index, row in previous.items() if index in current)
        final_value_matches = sum(current[index]["draft_sleep"] == value for index, value in measurement["expected_final"].items() if index in current)
        report["write_evidence"] = {
            "rows_before": len(previous), "rows_after": len(current), "rows_with_advanced_updated_at": advanced,
            "published_answers_unchanged": published_unchanged, "final_draft_value_matches_last_successful_write": final_value_matches,
            "successful_http_writes": successful_writes, "table_updates_delta": after["table_updates"] - before["table_updates"],
            "before_max_updated_at": max(row["updated_at"] for row in previous.values()),
            "after_min_updated_at": min(row["updated_at"] for row in current.values()),
            "after_max_updated_at": max(row["updated_at"] for row in current.values()),
            "published_before_sha256": hashlib.sha256(json.dumps([previous[index]["published_hash"] for index in sorted(previous)]).encode()).hexdigest(),
            "published_after_sha256": hashlib.sha256(json.dumps([current[index]["published_hash"] for index in sorted(current)]).encode()).hexdigest(),
            "draft_before_sha256": hashlib.sha256(json.dumps([previous[index]["draft_hash"] for index in sorted(previous)]).encode()).hexdigest(),
            "draft_after_sha256": hashlib.sha256(json.dumps([current[index]["draft_hash"] for index in sorted(current)]).encode()).hexdigest(),
        }
        run(fixture["invariant_command"], timeout=120)
        total = len(stats["status"])
        failures = sum(status >= 500 for status in stats["status"])
        unexpected = sum(status >= 400 and status not in fixture.get("expected_conflicts", []) for status in stats["status"])
        report.update(read_p95_ms=percentile(stats["read_ms"], .95), write_p95_ms=percentile(stats["write_ms"], .95),
                      matching_p95_ms=percentile(stats["matching_ms"], .95),
                      auth_p95_ms=percentile(stats["auth_ms"], .95), requests=total, http_5xx=failures,
                      http_5xx_ratio=failures / max(total, 1), unexpected_http_errors=unexpected,
                      invariant_checks="passed-before-and-after", privacy_violations=len(privacy_violations),
                      protocol_violations=len(protocol_violations),
                      endpoints={name: {"requests": len(values["ms"]), "p95_ms": percentile(values["ms"], .95),
                                        "successful_2xx": sum(200 <= status < 300 for status in values["status"]),
                                        "status_counts": {str(status): values["status"].count(status) for status in set(values["status"])}}
                                 for name, values in endpoints.items()},
                      status_counts={str(status): stats["status"].count(status) for status in set(stats["status"])})
        if not stats["read_ms"] or not stats["write_ms"] or not stats["matching_ms"] or any(not row["successful_2xx"] for row in report["endpoints"].values()):
            raise OpsError("The measurement did not successfully exercise every endpoint, matching reads and meaningful writes.")
        if (report["read_p95_ms"] > 500 or report["matching_p95_ms"] > 500 or report["write_p95_ms"] > 1000
                or report["http_5xx_ratio"] > .01 or unexpected or privacy_violations or protocol_violations):
            raise OpsError("Workload exceeded acceptance latency/error thresholds.")
        if (set(previous) != set(range(50)) or set(current) != set(range(50)) or advanced != 50
                or published_unchanged != 50 or final_value_matches != 50 or not successful_writes
                or report["write_evidence"]["table_updates_delta"] < successful_writes):
            raise OpsError("The database did not prove real draft updates for every actor with unchanged published answers.")
        report["status"] = "passed"
    except Exception as error:  # noqa: BLE001 - redact all worker failures in the saved report
        report["error"] = str(error) if isinstance(error, OpsError) else type(error).__name__
    finally:
        report.update(finished_at=now(), duration_seconds=round(time.monotonic() - started, 2),
                      auth_status_counts={str(status): stats["auth_status"].count(status) for status in set(stats["auth_status"])})
        write_report(args.report, report)
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
