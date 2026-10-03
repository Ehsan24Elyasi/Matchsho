"""Matchsho pilot API. Run schema migrations separately via pilot.migrate."""
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from database import Base, engine, get_db
from pilot import accounts, config, housing, invitations, matching, questionnaire, security
from pilot.domain_events import before_mutation, request_context
from pilot.domain_models import Invitation

logger = logging.getLogger("matchsho")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
app = FastAPI(title="مچ‌شو", version="3.0.0", docs_url=None if config.ENVIRONMENT == "production" else "/docs",
              redoc_url=None, openapi_url=None if config.ENVIRONMENT == "production" else "/openapi.json")
allowed_hosts = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,backend").split(",") if x.strip()]
if config.ENVIRONMENT == "production" and (not allowed_hosts or "*" in allowed_hosts):
    raise RuntimeError("Production requires explicit ALLOWED_HOSTS")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
if origins:
    if "*" in origins or config.ENVIRONMENT == "production":
        raise RuntimeError("Use same-origin production; development CORS origins must be explicit")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Matchsho-Protocol"])


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    request.state.request_id = incoming if re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", incoming) else uuid.uuid4().hex
    context_token = request_context.set(request.state.request_id)
    start = time.monotonic()
    protocol = request.headers.get("X-Matchsho-Protocol")
    try:
        if protocol and protocol != "3":
            response = JSONResponse(status_code=409, content={"detail": "نسخهٔ برنامه تغییر کرده است؛ صفحه را دوباره بارگذاری کنید", "code": "client_version"})
        else:
            response = await call_next(request)
    finally:
        request_context.reset(context_token)
    response.headers.update({"X-Request-ID": request.state.request_id, "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Matchsho-Protocol": "3"})
    route = request.scope.get("route")
    logger.info(json.dumps({"event": "http_request", "request_id": request.state.request_id,
                           "method": request.method, "route": getattr(route, "path", "unmatched"),
                           "status": response.status_code, "latency_ms": round((time.monotonic() - start) * 1000, 2)}))
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    logger.warning("database_conflict request_id=%s", request.state.request_id)
    return JSONResponse(status_code=409, content={"detail": "وضعیت هم‌زمان تغییر کرده یا این رکورد وجود دارد؛ صفحه را تازه کنید"})


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's input/ctx can contain raw credentials, tokens or private answers.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "type": error["type"], "msg": error["msg"]} for error in exc.errors()]})


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("database_unavailable type=%s request_id=%s", type(exc).__name__, request.state.request_id)
    return JSONResponse(status_code=503, content={"detail": "سرویس موقتاً در دسترس نیست؛ دوباره تلاش کنید"}, headers={"Retry-After": "5"})


for router in (security.router, accounts.router, questionnaire.router, matching.router, invitations.router, housing.router):
    app.include_router(router)


@app.get("/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    try:
        alembic_config = Config(str(Path(__file__).parent / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
        expected = set(ScriptDirectory.from_config(alembic_config).get_heads())
        with engine.connect() as connection:
            revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            schema = inspect(connection)
            if revisions != expected or not set(Base.metadata.tables) <= set(schema.get_table_names()):
                raise ValueError("schema mismatch")
            for table in Base.metadata.sorted_tables:
                if not set(table.columns.keys()) <= {c["name"] for c in schema.get_columns(table.name)}:
                    raise ValueError("column mismatch")
        return {"status": "ready", "schema": sorted(expected)}
    except Exception:
        raise HTTPException(503, "schema_or_database_unavailable") from None


@app.get("/pilot/config")
def pilot_config():
    return {"institution": config.INSTITUTION_NAME, "cycle": config.ACTIVE_CYCLE,
            "support_contact": config.SUPPORT_CONTACT, "scoring_version": "2", "protocol": "3",
            "retention": {"audit_days": config.AUDIT_RETENTION_DAYS, "report_days": config.REPORT_RETENTION_DAYS,
                          "closed_allocation_days": 90, "backup_days": 30},
            "privacy_notice": "پاسخ‌های پرسشنامه خصوصی‌اند. پیشنهاد هم‌اتاقی به معنی رزرو اتاق نیست؛ تخصیص نهایی با مدیریت خوابگاه است."}


@app.get("/admin/requests")
def operator_requests(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                      q: str = Query("", max_length=100), admin=Depends(security.require_admin), db=Depends(get_db)):
    before_mutation(db)
    query = db.query(Invitation).order_by(Invitation.id.desc())
    if q:
        query = query.filter(Invitation.status == q)
    rows = query.offset((page - 1) * limit).limit(limit).all()
    for inv in rows:
        invitations.synchronize(db, inv)
    result = {"items": [invitations.dto(db, inv, admin) for inv in rows], "total": query.count(), "page": page, "limit": limit}
    db.commit()
    return result
