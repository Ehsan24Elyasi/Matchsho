"""Read-only role journeys against the quarantined restored DB via the real ASGI app."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    if os.environ.get("NO_OUTBOUND_EMAIL", "").lower() != "true" or not os.environ.get("DATABASE_URL"):
        raise SystemExit("Restore smoke requires explicit DATABASE_URL and NO_OUTBOUND_EMAIL=true.")
    required = ("RESTORE_STUDENT_EMAIL", "RESTORE_STUDENT_PASSWORD", "RESTORE_OPERATOR_EMAIL", "RESTORE_OPERATOR_PASSWORD")
    if any(not os.environ.get(key) for key in required):
        raise SystemExit("Supply nominated restored student/operator credentials through restricted environment variables.")
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    from fastapi.testclient import TestClient
    from main import app

    def login(client, prefix):
        result = client.get("/auth/csrf")
        assert result.status_code == 200, "CSRF endpoint failed"
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        result = client.post("/auth/login", json={"email": os.environ[f"{prefix}_EMAIL"],
                                                 "password": os.environ[f"{prefix}_PASSWORD"]})
        assert result.status_code == 200, "Nominated restore account could not authenticate"

    with TestClient(app, base_url="http://localhost") as student:
        assert student.get("/health/ready").status_code == 200, "Restored schema is not ready"
        login(student, "RESTORE_STUDENT")
        for path in ("/me", "/questionnaire/me", "/matches?limit=12", "/requests", "/notifications"):
            assert student.get(path).status_code == 200, f"Student smoke failed at {path}"
        assert student.get("/group/me").status_code in {200, 404}, "Group state is inconsistent"
        assert student.get("/admin/groups").status_code == 403, "Student has operator access"
        matches = student.get("/matches?limit=12").json()
        for item in matches.get("items", []):
            assert not ({"email", "student_id", "answers"} & set((item.get("user") or {}).keys())), "Peer privacy regression"
    with TestClient(app, base_url="http://localhost") as operator:
        login(operator, "RESTORE_OPERATOR")
        for path in ("/admin/groups", "/admin/rooms", "/admin/cases", "/admin/audit"):
            assert operator.get(path).status_code == 200, f"Operator smoke failed at {path}"
    print("Restore student/operator role smoke passed; no email was enabled.")


if __name__ == "__main__":
    main()
