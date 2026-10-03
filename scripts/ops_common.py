"""Small shared operational guards. Credentials never appear in subprocess arguments."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

REMOTE_TYPES = {"s3", "b2", "azureblob", "sftp", "swift", "drive", "onedrive"}


class OpsError(RuntimeError):
    pass


def run(command: list[str], *, env: dict | None = None, timeout: int = 60) -> str:
    try:
        completed = subprocess.run(command, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OpsError(f"{command[0]} unavailable or timed out; inspect local tooling.") from error
    if completed.returncode:
        # Tool errors can contain connection strings/tokens. Do not echo their stderr.
        raise OpsError(f"{command[0]} failed with code {completed.returncode}; use restricted operator diagnostics.")
    return completed.stdout.strip()


def database_env(raw: str, *, development: bool = False) -> tuple[dict[str, str], tuple[str, int, str]]:
    parsed = urlsplit(raw.replace("postgresql+psycopg2://", "postgresql://", 1))
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise OpsError("A PostgreSQL URL with explicit hostname is required.")
    options = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(value) != 1 for value in options.values()):
        raise OpsError("Duplicate PostgreSQL URL options are not allowed.")
    sslmode = options.get("sslmode", [""])[0]
    if not development and (sslmode != "verify-full" or not options.get("sslrootcert")):
        raise OpsError("Remote operations require sslmode=verify-full and sslrootcert.")
    if development and parsed.hostname not in {"localhost", "127.0.0.1", "::1", "postgres", "restore-postgres"}:
        raise OpsError("Development TLS exception is only for an isolated local database.")
    name = unquote(parsed.path.lstrip("/"))
    if not re.fullmatch(r"[a-zA-Z0-9_]+", name):
        raise OpsError("Use an explicit database name containing only letters, digits and underscores.")
    env = os.environ.copy()
    # Explicitly replace inherited libpq options; never inherit a production service.
    for key in list(env):
        if key.startswith("PG"):
            env.pop(key)
    env.update(PGHOST=parsed.hostname, PGPORT=str(parsed.port or 5432), PGDATABASE=name,
               PGUSER=unquote(parsed.username or ""), PGPASSWORD=unquote(parsed.password or ""),
               PGSSLMODE=sslmode or "disable", PGCONNECT_TIMEOUT="10", PGAPPNAME="matchsho-ops")
    for option, variable in {"sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY"}.items():
        if option in options:
            env[variable] = options[option][0]
    return env, (parsed.hostname.lower(), parsed.port or 5432, name)


def sql(query: str, env: dict[str, str]) -> str:
    return run(["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set", "ON_ERROR_STOP=1", "--command", query], env=env)


def database_identity(env: dict[str, str]) -> str:
    return sql("SELECT current_database() || '|' || COALESCE(inet_server_addr()::text,'local') || '|' || COALESCE(inet_server_port()::text,'local')", env)


def remote_guard(remote: str, config: dict) -> None:
    match = re.fullmatch(r"([A-Za-z0-9_-]+):([^\\]+)", remote)
    if not match:
        raise OpsError("Backup destination must be a configured off-host rclone remote with an explicit prefix.")
    name, prefix = match.groups()
    if config.get(name, {}).get("type") not in REMOTE_TYPES:
        raise OpsError("Backup remote must be an off-host s3/b2/azureblob/sftp/swift/drive/onedrive backend.")
    parts = prefix.strip("/").split("/")
    if len(parts) < 2 or parts[-1] != "matchsho-backups" or ".." in parts:
        raise OpsError("Destination must end with <dedicated-prefix>/matchsho-backups; remote root is forbidden.")


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def now() -> str:
    return datetime.now(UTC).isoformat()
