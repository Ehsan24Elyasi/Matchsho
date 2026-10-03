#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR/backend"

if [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "venv/bin/activate"
fi

# Run `python -m pilot.migrate` once in the release job before starting replicas.
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers --no-access-log
