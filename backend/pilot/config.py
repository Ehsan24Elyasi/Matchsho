"""Validated, shared configuration for the pilot API and worker."""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-matchsho-secret-change-before-deployment")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
ACTIVE_CYCLE = os.getenv("ACTIVE_CYCLE", "pilot-2026")
INSTITUTION_NAME = os.getenv("INSTITUTION_NAME", "پایلوت مچ‌شو")
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "مدیریت خوابگاه")
ALLOWED_POOLS = tuple(p.strip() for p in os.getenv("ALLOWED_POOLS", "male,female").split(",") if p.strip())
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
LOGIN_ACCOUNT_LIMIT = int(os.getenv("LOGIN_ACCOUNT_LIMIT", "20"))
LOGIN_IP_LIMIT = int(os.getenv("LOGIN_IP_LIMIT", "200"))
CLAIM_ID_LIMIT = int(os.getenv("CLAIM_ID_LIMIT", "3"))
CLAIM_IP_LIMIT = int(os.getenv("CLAIM_IP_LIMIT", "60"))
EMAIL_RECIPIENT_LIMIT = int(os.getenv("EMAIL_RECIPIENT_LIMIT", "3"))
EMAIL_IP_LIMIT = int(os.getenv("EMAIL_IP_LIMIT", "60"))
EMAIL_COOLDOWN_SECONDS = int(os.getenv("EMAIL_COOLDOWN_SECONDS", "60"))
TOKEN_IP_LIMIT = int(os.getenv("TOKEN_IP_LIMIT", "200"))
ARGON2_CONCURRENCY = int(os.getenv("ARGON2_CONCURRENCY", "2"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "90"))
REPORT_RETENTION_DAYS = int(os.getenv("REPORT_RETENTION_DAYS", "30"))
OUTBOX_RETENTION_DAYS = int(os.getenv("OUTBOX_RETENTION_DAYS", "30"))
OUTBOX_MAX_ATTEMPTS = int(os.getenv("OUTBOX_MAX_ATTEMPTS", "6"))
OUTBOX_LEASE_SECONDS = int(os.getenv("OUTBOX_LEASE_SECONDS", "120"))
OUTBOX_KEY_VERSION = os.getenv("OUTBOX_KEY_VERSION", "1")
OUTBOX_KEYS = json.loads(os.getenv("OUTBOX_KEYS_JSON", "{}"))
_key = os.getenv("OUTBOX_KEY", "")
if _key:
    OUTBOX_KEYS[OUTBOX_KEY_VERSION] = _key
elif ENVIRONMENT != "production" and OUTBOX_KEY_VERSION not in OUTBOX_KEYS:
    OUTBOX_KEYS[OUTBOX_KEY_VERSION] = base64.urlsafe_b64encode(
        hashlib.sha256(b"matchsho-local-mail-only-key-do-not-use-in-production").digest()
    ).decode()
if OUTBOX_KEY_VERSION not in OUTBOX_KEYS:
    raise RuntimeError("OUTBOX_KEY or OUTBOX_KEYS_JSON must configure the active outbox key")
for _version, _configured_key in OUTBOX_KEYS.items():
    Fernet(_configured_key.encode())
if COOKIE_SAMESITE not in {"lax", "strict", "none"} or (COOKIE_SAMESITE == "none" and not COOKIE_SECURE):
    raise RuntimeError("Invalid cookie security configuration")
if ENVIRONMENT == "production":
    if len(SECRET_KEY) < 32 or SECRET_KEY.startswith("development-"):
        raise RuntimeError("Production requires an independent strong SECRET_KEY")
    if not COOKIE_SECURE or not PUBLIC_BASE_URL.startswith("https://"):
        raise RuntimeError("Production requires Secure cookies and HTTPS PUBLIC_BASE_URL")
    if SECRET_KEY in OUTBOX_KEYS.values():
        raise RuntimeError("Outbox encryption key must be independent from SECRET_KEY")
    if os.getenv("SMTP_SECURITY", "starttls") not in {"starttls", "tls"}:
        raise RuntimeError("Production SMTP must use TLS")
if not 1 <= AUDIT_RETENTION_DAYS <= 90 or not 1 <= REPORT_RETENTION_DAYS <= 30 or not 1 <= OUTBOX_RETENTION_DAYS <= 30:
    raise RuntimeError("Retention exceeds published pilot bounds")
if any(value < 1 for value in (ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS, LOGIN_ACCOUNT_LIMIT,
       LOGIN_IP_LIMIT, CLAIM_ID_LIMIT, CLAIM_IP_LIMIT, EMAIL_RECIPIENT_LIMIT, EMAIL_IP_LIMIT,
       EMAIL_COOLDOWN_SECONDS, TOKEN_IP_LIMIT, ARGON2_CONCURRENCY, OUTBOX_MAX_ATTEMPTS, OUTBOX_LEASE_SECONDS)):
    raise RuntimeError("Security limits must be positive")
