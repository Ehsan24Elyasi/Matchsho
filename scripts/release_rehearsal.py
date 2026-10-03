"""Exercise failed migration and safe image rollback in a separate disposable stack."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-disposable", action="store_true", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = "matchsho-rehearsal-" + uuid.uuid4().hex[:8]
    private = root / "artifacts/pilot/private" / project
    private.mkdir(parents=True)
    report = {"kind": "local-staging-release-rehearsal", "started_at": datetime.now(timezone.utc).isoformat(),
              "project": project, "disposable": True, "production_release_authorized": False,
              "scope": "Synthetic safe release B and rollback to current guarded release A; not a prior production release.",
              "checks": {}}

    def run(argv, *, check=True, cwd=None, timeout=180):
        result = subprocess.run(argv, cwd=cwd or root, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, check=False)
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({argv[0]} {argv[1]}): {result.stderr[-2000:]}")
        return result

    def request(path, *, protocol=None, method="GET"):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     headers={"X-Matchsho-Protocol": protocol} if protocol else {})
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, response.read(), dict(response.headers)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    backend = run(["docker", "image", "inspect", "matchsho-backend:local-test", "--format", "{{.Id}}"] ).stdout.strip()
    frontend = run(["docker", "image", "inspect", "matchsho-frontend:local-test", "--format", "{{.Id}}"] ).stdout.strip()
    safe_tag, next_tag = project + ":safe", project + ":next"
    run(["docker", "tag", frontend, safe_tag])
    report["images"] = {"backend": backend, "safe_frontend": frontend}
    password = uuid.uuid4().hex
    environment = {"ENVIRONMENT": "development", "SECRET_KEY": uuid.uuid4().hex + uuid.uuid4().hex,
                   "DATABASE_URL": f"postgresql+psycopg2://fixture:{password}@postgres/rehearsal_test?sslmode=disable",
                   "ALLOWED_HOSTS": "localhost,127.0.0.1,matchsho-backend", "NO_OUTBOUND_EMAIL": "true"}
    app = {"image": backend, "environment": environment, "read_only": True, "tmpfs": ["/tmp"]}
    services = {
        "postgres": {"image": "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea",
                     "environment": {"POSTGRES_USER": "fixture", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "rehearsal_test"},
                     "healthcheck": {"test": ["CMD", "pg_isready", "-U", "fixture", "-d", "rehearsal_test"],
                                     "interval": "1s", "timeout": "2s", "retries": 40}},
        "migrate": {**app, "command": ["python", "-m", "pilot.migrate"], "healthcheck": {"disable": True},
                    "depends_on": {"postgres": {"condition": "service_healthy"}}},
        "matchsho-backend": {**app, "depends_on": {"migrate": {"condition": "service_completed_successfully"}},
                             "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')"],
                                             "interval": "2s", "timeout": "3s", "retries": 40}},
        "frontend": {"image": safe_tag, "depends_on": {"matchsho-backend": {"condition": "service_healthy"}},
                     "ports": [f"127.0.0.1:{port}:8080"], "read_only": True,
                     "tmpfs": ["/tmp", "/var/cache/nginx:uid=101,gid=101", "/var/run:uid=101,gid=101"]}}
    compose_file = private / "compose.json"

    def save():
        compose_file.write_text(json.dumps({"services": services}), encoding="utf-8")

    def compose(*argv, check=True):
        return run(["docker", "compose", "-p", project, "-f", str(compose_file), *argv], check=check)

    def sql(statement):
        return compose("exec", "-T", "postgres", "psql", "-U", "fixture", "-d", "rehearsal_test", "-Atc", statement).stdout.strip()

    try:
        save()
        compose("up", "-d", "--wait", "--wait-timeout", "100")
        status, first_html, headers = request("/")
        assert status == 200 and "no-cache" in headers["Cache-Control"]
        first_manifest = json.loads(request("/asset-manifest.json")[1])
        asset = first_manifest["assetPrefix"] + "/js/landing.js"
        assert "immutable" in request(asset)[2]["Cache-Control"]
        sql("CREATE TABLE rehearsal_preserved (id integer primary key); INSERT INTO rehearsal_preserved VALUES (1)")
        report["checks"]["release_a_ready"] = True

        failure = private / "9999_rehearsal_failure.py"
        failure.write_text("from alembic import op\nrevision='9999_rehearsal'\ndown_revision='0002_pilot'\nbranch_labels=None\ndepends_on=None\ndef upgrade():\n    op.execute('CREATE TABLE rehearsal_must_rollback (id integer)')\n    raise RuntimeError('intentional disposable migration failure')\ndef downgrade():\n    raise RuntimeError('not supported')\n", encoding="utf-8")
        compose("stop", "frontend", "matchsho-backend")
        services["migrate"]["volumes"] = [f"{failure.as_posix()}:/app/alembic/versions/9999_rehearsal_failure.py:ro"]
        save()
        failed = compose("up", "--force-recreate", "--exit-code-from", "migrate", "migrate", check=False)
        assert failed.returncode != 0
        gated = compose("up", "-d", "matchsho-backend", check=False)
        assert gated.returncode != 0
        running = compose("ps", "--status", "running", "--services").stdout.split()
        assert "matchsho-backend" not in running
        assert sql("SELECT version_num FROM alembic_version") == "0002_pilot"
        assert sql("SELECT to_regclass('public.rehearsal_must_rollback') IS NULL") == "t"
        assert sql("SELECT count(*) FROM rehearsal_preserved") == "1"
        report["checks"]["failed_migration_rolled_back_and_api_gated"] = True
        del services["migrate"]["volumes"]
        save()
        compose("up", "-d", "--wait", "--wait-timeout", "100")

        # Build an inert source variation through the same asset fingerprint builder.
        source = private / "frontend"
        source.mkdir()
        for folder in ("js", "src/fonts", "scripts"):
            shutil.copytree(root / "frontend" / folder, source / folder)
        for name in ("index.html", "about.html", "privacy.html", "styles.css", "dashboard/index_dashboard.html", "dashboard/admin.html"):
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / "frontend" / name, destination)
        with (source / "js/landing.js").open("a", encoding="utf-8") as handle:
            handle.write("\n// Disposable release-rehearsal marker.\n")
        run(["node", "scripts/build.mjs"], cwd=source)
        (source / "Dockerfile").write_text(f"FROM {safe_tag}\nCOPY dist /usr/share/nginx/html\n", encoding="utf-8")
        run(["docker", "build", "-q", "-t", next_tag, str(source)])
        services["frontend"]["image"] = next_tag
        save()
        compose("up", "-d", "--no-deps", "frontend")
        time.sleep(2)
        second_manifest = json.loads(request("/asset-manifest.json")[1])
        assert second_manifest["version"] != first_manifest["version"]
        assert second_manifest["assetPrefix"].encode() in request("/")[1]
        status, body, _ = request("/api/claim", protocol="2", method="POST")
        assert status == 409 and json.loads(body)["code"] == "client_version"
        assert sql("SELECT count(*) FROM users") == "0"
        report["checks"]["new_assets_and_stale_protocol_rejected_before_mutation"] = True
        report["asset_versions"] = [first_manifest["version"], second_manifest["version"]]

        services["frontend"]["image"] = safe_tag
        save()
        compose("up", "-d", "--no-deps", "frontend")
        time.sleep(2)
        assert request("/")[1] == first_html
        assert request("/api/health/ready")[0] == 200
        assert sql("SELECT version_num FROM alembic_version") == "0002_pilot"
        assert sql("SELECT count(*) FROM rehearsal_preserved") == "1"
        report["checks"]["compatible_rollback_preserves_schema_data_and_assets"] = True
        report["html_sha256"] = hashlib.sha256(first_html).hexdigest()
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        compose("down", "--volumes", check=False)
        run(["docker", "image", "rm", safe_tag, next_tag], check=False)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "checks": report["checks"], "report": str(args.report)}))


if __name__ == "__main__":
    main()
