"""Database configuration and session management."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
EXPLICIT_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_SSLMODE = os.getenv("DB_SSLMODE", "verify-full" if ENVIRONMENT == "production" else "prefer").lower()

if DB_POOL_SIZE < 1 or DB_MAX_OVERFLOW < 0 or DB_POOL_TIMEOUT < 1:
    raise RuntimeError("Database pool settings are invalid")

def validate_database_url(value, environment=ENVIRONMENT):
    url = make_url(value)
    if environment == "production":
        if url.get_backend_name() != "postgresql" or url.query.get("sslmode") != "verify-full":
            raise RuntimeError("Production effective DATABASE_URL must use PostgreSQL sslmode=verify-full")
        ca = url.query.get("sslrootcert")
        if not isinstance(ca, str) or not Path(ca).is_file():
            raise RuntimeError("Production effective DATABASE_URL requires an existing sslrootcert CA file")
        if not url.host or not url.database or "options" in url.query:
            raise RuntimeError("Production database host/database must be explicit; options overrides are prohibited")
    return url

if EXPLICIT_DATABASE_URL:
    validate_database_url(EXPLICIT_DATABASE_URL)
    SQLALCHEMY_DATABASE_URL = EXPLICIT_DATABASE_URL
    connect_args = {"check_same_thread": False} if EXPLICIT_DATABASE_URL.startswith("sqlite") else {}
    pool_options = (
        {}
        if EXPLICIT_DATABASE_URL.startswith("sqlite")
        else {
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
            "pool_timeout": DB_POOL_TIMEOUT,
            "pool_recycle": 1800,
        }
    )
    engine = create_engine(EXPLICIT_DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, **pool_options)
elif DB_TYPE == "sqlite":
    if ENVIRONMENT == "production":
        raise RuntimeError("Production requires PostgreSQL with certificate verification")
    # Keep the incompatible legacy database.db untouched and use a new file.
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{(BASE_DIR / 'database_v2.db').as_posix()}"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
elif DB_TYPE == "postgresql":
    db_user = quote_plus(os.getenv("DB_USER", "postgres"))
    db_password = quote_plus(os.getenv("DB_PASSWORD", ""))
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = quote_plus(os.getenv("DB_NAME", "matchsho"))
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?sslmode={DB_SSLMODE}"
    )
    if os.getenv("DB_SSLROOTCERT"):
        SQLALCHEMY_DATABASE_URL += "&sslrootcert=" + quote_plus(os.environ["DB_SSLROOTCERT"])
    validate_database_url(SQLALCHEMY_DATABASE_URL)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=1800,
    )
else:
    raise ValueError(f"Unknown DB_TYPE: {DB_TYPE}")


# Quota commits must not queue behind business connections which are waiting
# for the domain lock. Use the exact same validated URL, with a small dedicated
# pool; SQLite unit fixtures may keep their caller bind or attach an isolated one.
if engine.dialect.name == "postgresql":
    engine.rate_limit_bind = create_engine(
        SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_size=2, max_overflow=2,
        pool_timeout=5, pool_recycle=1800,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
