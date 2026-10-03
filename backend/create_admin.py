"""Create the initial administrator from environment variables.

Run this as a one-off deployment task. The web process does not need access to
the initial administrator password in production.
"""

import os
import secrets

from argon2 import PasswordHasher

from database import SessionLocal
from models import User


def main() -> None:
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        raise SystemExit("ADMIN_EMAIL and an ADMIN_PASSWORD of at least 12 characters are required")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if existing.role != "admin":
                raise SystemExit("The configured email already belongs to a non-admin user")
            if not existing.email_verified:
                existing.email_verified = True
                db.commit()
            print("Administrator already exists")
            return
        db.add(
            User(
                email=email,
                password_hash=PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password),
                name="Administrator",
                class_name="Administration",
                student_id=f"admin-{secrets.token_hex(6)}",
                gender="other",
                role="admin",
                email_verified=True,
            )
        )
        db.commit()
        print("Administrator created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
