"""Create a fresh, local-only Compose environment without reading production .env."""
from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--mailpit-port", type=int, default=8025)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 1024 <= args.mailpit_port <= 65535:
        parser.error("Use unprivileged ports from 1024 to 65535.")
    path = args.output.resolve()
    if path.name in {".env", ".env.production"}:
        parser.error("Use a dedicated local/test filename, never a live environment file.")
    values = {
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "SECRET_KEY": secrets.token_hex(48),
        "OUTBOX_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "ADMIN_EMAIL": "operator@example.com",
        "ADMIN_PASSWORD": secrets.token_urlsafe(30),
        "FRONTEND_PORT": str(args.port),
        "MAILPIT_PORT": str(args.mailpit_port),
        "RELEASE_ID": "local-test",
        "REQUIRE_EMAIL_VERIFICATION": "false",
    }
    # Exclusive creation prevents accidental replacement of an existing environment.
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write("# LOCAL DISPOSABLE ENVIRONMENT. Never use for real users.\n")
        stream.writelines(f"{key}={value}\n" for key, value in values.items())
    print(f"Created local-only environment at {path}; credentials were not printed.")


if __name__ == "__main__":
    main()
