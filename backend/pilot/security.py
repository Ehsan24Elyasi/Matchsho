"""Database-backed authentication, one-time roster claims and shared throttling."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore
from urllib.parse import quote

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, User
from pilot import config
from pilot.security_models import AccountSession, DeletionLedger, Enrollment, RateBucket, SecurityToken
from pilot.security_schemas import ClaimRequest, Credentials, EmailInput, PasswordToken, TokenInput

router = APIRouter()
logger = logging.getLogger("matchsho.security")
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_argon2_slots = BoundedSemaphore(config.ARGON2_CONCURRENCY)
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(40))
GENERIC_MESSAGE = {"message": "اگر اطلاعات واجد شرایط باشد، پیام در صف ارسال قرار می‌گیرد.", "status": "queued"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_digest(value: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def normalize_identity(value: str) -> str:
    return value.strip().lower().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(value: str) -> str:
    with _argon2_slots:
        return password_hasher.hash(value)


def verify_password(stored: str, value: str) -> bool:
    with _argon2_slots:
        try:
            return password_hasher.verify(stored, value)
        except (VerificationError, InvalidHashError):
            return False


def client_ip(request: Request) -> str:
    # Uvicorn resolves headers only from explicitly configured proxy peers.
    return request.client.host if request.client else "unknown"


def security_audit(db: Session, action: str, user_id: int | None, target: str = "", request: Request | None = None):
    db.add(AuditLog(actor_user_id=user_id, action=action, target_type="security", target_id=target[:50],
                    ip_address=client_ip(request) if request else None))
    logger.info("security_event action=%s actor=%s target=%s request_id=%s", action, user_id, target[:50],
                getattr(request.state, "request_id", "-") if request else "-")


def throttle(db: Session, action: str, identifier: str, limit: int, seconds: int, *, cooldown=False):
    """Charge in a separate committed transaction, even when the caller rolls back.

    SQLite is supported for unit tests. Production is PostgreSQL and uses one
    atomic UPSERT RETURNING for each counter shared by all API/worker processes.
    """
    try:
        business_bind = db.get_bind()
        business_engine = getattr(business_bind, "engine", business_bind)
        limiter_bind = getattr(business_engine, "rate_limit_bind", business_engine)
        with Session(bind=limiter_bind) as limiter:
            current = aware(limiter.scalar(select(func.current_timestamp())))
            window = "cooldown" if cooldown else str(int(current.timestamp()) // seconds)
            key = keyed_digest(f"{action}:{identifier.strip().lower()}:{window}")
            expiry = current + timedelta(seconds=seconds) if cooldown else datetime.fromtimestamp(
                (int(current.timestamp()) // seconds + 1) * seconds, timezone.utc)
            if limiter.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            statement = insert(RateBucket).values(key=key, attempts=1, expires_at=expiry)
            if cooldown:
                statement = statement.on_conflict_do_update(index_elements=[RateBucket.key],
                    set_={"attempts": 1, "expires_at": expiry}, where=RateBucket.expires_at <= current)
            else:
                statement = statement.on_conflict_do_update(index_elements=[RateBucket.key],
                    set_={"attempts": RateBucket.attempts + 1})
            result = limiter.execute(statement.returning(RateBucket.attempts, RateBucket.expires_at)).first()
            limiter.commit()
        if result is None or result.attempts > limit:
            retry = max(1, int((aware(result.expires_at) - current).total_seconds())) if result else seconds
            logger.warning("security_event action=rate_limited category=%s", action)
            raise HTTPException(429, "تعداد تلاش‌ها بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.",
                                headers={"Retry-After": str(retry)})
    except SQLAlchemyError as exc:
        logger.error("security_event action=limiter_unavailable error_type=%s", type(exc).__name__)
        raise HTTPException(503, "کنترل امنیت موقتاً در دسترس نیست.", headers={"Retry-After": "30"}) from None


def email_throttle(db, request, recipient):
    throttle(db, "email-ip", client_ip(request), config.EMAIL_IP_LIMIT, 3600)
    throttle(db, "email-recipient", recipient, config.EMAIL_RECIPIENT_LIMIT, 3600)
    throttle(db, "email-cooldown", recipient, 1, config.EMAIL_COOLDOWN_SECONDS, cooldown=True)


def require_csrf(request: Request):
    cookie = request.cookies.get("csrf_token", "")
    header = request.headers.get("X-CSRF-Token", "")
    if not cookie or not header or len(cookie) > 200 or len(header) > 200 or not hmac.compare_digest(cookie.encode(), header.encode()):
        raise HTTPException(403, "اثبات امنیت درخواست معتبر نیست؛ صفحه را دوباره بارگذاری کنید.")


def decode_token(raw: str, kind: str) -> dict:
    try:
        data = jwt.decode(raw, config.SECRET_KEY, algorithms=["HS256"],
                          options={"require": ["sub", "sid", "auth_version", "type", "exp", "iat"]})
        if data["type"] != kind or not str(data["sub"]).isdigit() or not isinstance(data["sid"], str):
            raise ValueError()
        if kind == "refresh" and not isinstance(data.get("jti"), str):
            raise ValueError()
        return data
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "نشست معتبر نیست؛ دوباره وارد شوید.") from None


def _raw_access(request: Request):
    raw = request.cookies.get("access_token")
    if not raw and request.headers.get("authorization", "").lower().startswith("bearer "):
        raw = request.headers["authorization"][7:]
    return raw


def valid_user(user):
    return user and user.is_active and user.account_status == "active" and user.email_verified


def valid_session(session, user, data):
    return (session and session.user_id == user.id and session.revoked_at is None
            and aware(session.expires_at) > now()
            and session.auth_version == user.auth_version == data["auth_version"])


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = _raw_access(request)
    if not raw:
        raise HTTPException(401, "ابتدا وارد حساب شوید.")
    data = decode_token(raw, "access")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        # Serialize protected mutations before reading authorization. A request
        # waiting behind a suspension/demotion must see the committed new state.
        from pilot.domain_events import before_mutation
        before_mutation(db)
    user = db.get(User, int(data["sub"]))
    session = db.get(AccountSession, data["sid"])
    if not valid_user(user) or not valid_session(session, user, data):
        raise HTTPException(401, "نشست پایان یافته است؛ دوباره وارد شوید.")
    request.state.sid = session.sid
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است.")
    return user


def owner_user(user, db: Session | None = None):
    result = {key: getattr(user, key) for key in ("id", "email", "name", "class_name", "student_id", "gender",
        "role", "email_verified", "account_status", "discovery_consent", "explanation_consent", "consent_version", "notification_email")}
    if db is not None:
        enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id))
        result["eligibility"] = {"status": enrollment.status if enrollment else "unreconciled",
                                 "pool": enrollment.pool if enrollment else None,
                                 "cycle": enrollment.cycle if enrollment else None}
    return result


def revoke_all(db, user):
    user.auth_version += 1
    db.execute(update(AccountSession).where(AccountSession.user_id == user.id,
               AccountSession.revoked_at.is_(None)).values(revoked_at=now()))


def clear_cookies(response):
    for key in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(key, path="/", secure=config.COOKIE_SECURE, samesite=config.COOKIE_SAMESITE)
    response.headers["Cache-Control"] = "no-store"


def issue_cookies(response, user, session, refresh_jti):
    instant = now()
    base = {"sub": str(user.id), "sid": session.sid, "auth_version": user.auth_version, "iat": instant}
    access_expiry = min(instant + timedelta(minutes=config.ACCESS_TOKEN_MINUTES), aware(session.expires_at))
    access = jwt.encode({**base, "type": "access", "exp": access_expiry}, config.SECRET_KEY, algorithm="HS256")
    refresh = jwt.encode({**base, "type": "refresh", "exp": session.expires_at, "jti": refresh_jti},
                         config.SECRET_KEY, algorithm="HS256")
    options = {"path": "/", "secure": config.COOKIE_SECURE, "httponly": True, "samesite": config.COOKIE_SAMESITE}
    response.set_cookie("access_token", access, max_age=max(1, int((access_expiry - instant).total_seconds())), **options)
    response.set_cookie("refresh_token", refresh, max_age=max(1, int((aware(session.expires_at) - instant).total_seconds())), **options)
    response.headers["Cache-Control"] = "no-store"


def create_session(db, user, request):
    jti = secrets.token_urlsafe(32)
    session = AccountSession(sid=secrets.token_urlsafe(32), user_id=user.id, auth_version=user.auth_version,
                             refresh_digest=digest(jti), device=request.headers.get("user-agent", "Unknown device")[:160],
                             expires_at=now() + timedelta(days=config.REFRESH_TOKEN_DAYS))
    db.add(session)
    return session, jti


def queue_token(db, purpose, email, *, user=None, enrollment=None, lifetime_hours=1):
    from pilot.delivery import enqueue
    conditions = [SecurityToken.purpose == purpose, SecurityToken.used_at.is_(None),
                  SecurityToken.superseded_at.is_(None)]
    conditions.append(SecurityToken.user_id == user.id if user else SecurityToken.enrollment_id == enrollment.id)
    db.execute(update(SecurityToken).where(*conditions).values(superseded_at=now()))
    raw = secrets.token_urlsafe(48)
    token = SecurityToken(token_hash=digest(raw), purpose=purpose, approved_email=email,
                           user_id=user.id if user else None, enrollment_id=enrollment.id if enrollment else None,
                           expires_at=now() + timedelta(hours=lifetime_hours))
    db.add(token)
    db.flush()
    route = {"claim": "activate", "reset_password": "reset-password", "verify_email": "verify-email"}[purpose]
    link = f"{config.PUBLIC_BASE_URL}/dashboard/index_dashboard.html#{route}?token={quote(raw)}"
    enqueue(db, email, "پیوند امن مچ‌شو", f"برای ادامه از پیوند زیر استفاده کنید. اگر شما درخواست نداده‌اید، نادیده بگیرید.\n{link}",
            event_key=f"auth:{token.id}", purpose=purpose, token_id=token.id)
    return token


def usable_token(token, purpose):
    return (token and token.purpose == purpose and not token.used_at and not token.superseded_at
            and aware(token.expires_at) > now())


@router.get("/auth/csrf")
def csrf(response: Response, request: Request):
    value = request.cookies.get("csrf_token")
    if not value or len(value) < 32 or len(value) > 100:
        value = secrets.token_urlsafe(32)
    response.set_cookie("csrf_token", value, secure=config.COOKIE_SECURE, httponly=False,
                        samesite=config.COOKIE_SAMESITE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": value}


@router.get("/auth/me")
@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return owner_user(user, db)


@router.post("/auth/register", status_code=202, dependencies=[Depends(require_csrf)])
@router.post("/auth/resend-verification", status_code=202, dependencies=[Depends(require_csrf)])
def claim(data: ClaimRequest, request: Request, db: Session = Depends(get_db)):
    identity = normalize_identity(data.student_id)
    throttle(db, "claim-ip", client_ip(request), config.CLAIM_IP_LIMIT, 3600)
    throttle(db, "claim-identity", identity, config.CLAIM_ID_LIMIT, 3600)
    initial = db.scalar(select(Enrollment).where(Enrollment.student_id == identity))
    # Claim, resend and password recovery share the approved recipient budget.
    # Unknown identities are charged too and return the same public response.
    recipient_key = initial.email if initial else (normalize_email(str(data.email)) if data.email else identity)
    email_throttle(db, request, recipient_key)
    enrollment = db.scalar(select(Enrollment).where(Enrollment.student_id == identity)
                           .execution_options(populate_existing=True).with_for_update())
    legacy = db.scalar(select(User).where(User.student_id == identity)) if enrollment else None
    reclaimable = not legacy or (legacy.role == "user" and legacy.is_active and legacy.account_status == "active"
                                 and not db.get(DeletionLedger, legacy.id))
    if (enrollment and enrollment.status == "eligible" and enrollment.cycle == config.ACTIVE_CYCLE
            and enrollment.pool in config.ALLOWED_POOLS
            and reclaimable
            and (not data.email or normalize_email(str(data.email)) == enrollment.email)
            and (not enrollment.user_id or not valid_user(db.get(User, enrollment.user_id)))):
        queue_token(db, "claim", enrollment.email, enrollment=enrollment, lifetime_hours=24)
        db.commit()
    return GENERIC_MESSAGE


@router.post("/auth/activate", dependencies=[Depends(require_csrf)])
def activate(data: PasswordToken, request: Request, response: Response, db: Session = Depends(get_db)):
    from pilot.domain_events import account_changed, before_mutation
    throttle(db, "token-ip", client_ip(request), config.TOKEN_IP_LIMIT, 900)
    initial = db.scalar(select(SecurityToken).where(SecurityToken.token_hash == digest(data.token)))
    if not usable_token(initial, "claim"):
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    password_hash = hash_password(data.password)
    before_mutation(db)
    enrollment_initial = db.get(Enrollment, initial.enrollment_id)
    existing = db.scalar(select(User).where(User.student_id == enrollment_initial.student_id).with_for_update())
    enrollment = db.scalar(select(Enrollment).where(Enrollment.id == initial.enrollment_id)
                           .execution_options(populate_existing=True).with_for_update())
    token = db.scalar(select(SecurityToken).where(SecurityToken.id == initial.id)
                      .execution_options(populate_existing=True).with_for_update())
    if (not usable_token(token, "claim") or enrollment.status != "eligible"
            or enrollment.email != token.approved_email or enrollment.cycle != config.ACTIVE_CYCLE
            or enrollment.pool not in config.ALLOWED_POOLS
            or (enrollment.user_id and (not existing or enrollment.user_id != existing.id))
            or (existing and valid_user(existing) and enrollment.user_id)):
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    if existing and (existing.role != "user" or not existing.is_active or existing.account_status != "active"
                     or db.get(DeletionLedger, existing.id)):
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    user = existing or User(student_id=enrollment.student_id, role="user", auth_version=1)
    if existing:
        revoke_all(db, user)
    user.email = enrollment.email
    user.name, user.class_name, user.gender = enrollment.name, enrollment.class_name, enrollment.gender
    user.password_hash = password_hash
    user.is_active, user.email_verified, user.account_status = True, True, "active"
    user.discovery_consent, user.explanation_consent = False, False
    db.add(user)
    db.flush()
    enrollment.user_id = user.id
    token.used_at = now()
    account_changed(db, user, "enrollment")
    session, jti = create_session(db, user, request)
    security_audit(db, "enrollment.activated", user.id, str(enrollment.id), request)
    db.commit()
    issue_cookies(response, user, session, jti)
    return owner_user(user, db)


def login_user(data, request, response, db, admin_only=False):
    email = normalize_email(str(data.email))
    throttle(db, "login-ip", client_ip(request), config.LOGIN_IP_LIMIT, 900)
    throttle(db, "login-account", email, config.LOGIN_ACCOUNT_LIMIT, 900)
    # Credentials are checked while holding the user lock, serializing reset/login.
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    verified = verify_password(user.password_hash if user else _dummy_hash, data.password)
    if not verified or not valid_user(user) or (admin_only and user.role != "admin"):
        raise HTTPException(401, "ایمیل یا رمز عبور معتبر نیست.")
    session, jti = create_session(db, user, request)
    security_audit(db, "session.created", user.id, session.sid, request)
    db.commit()
    issue_cookies(response, user, session, jti)
    return owner_user(user, db)


@router.post("/auth/login", dependencies=[Depends(require_csrf)])
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    return login_user(data, request, response, db)


@router.post("/admin/login", dependencies=[Depends(require_csrf)])
def admin_login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    return login_user(data, request, response, db, True)


@router.post("/auth/refresh", dependencies=[Depends(require_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    data = decode_token(request.cookies.get("refresh_token", ""), "refresh")
    user = db.scalar(select(User).where(User.id == int(data["sub"])).with_for_update())
    session = db.scalar(select(AccountSession).where(AccountSession.sid == data["sid"]).with_for_update())
    if not valid_user(user) or not valid_session(session, user, data):
        raise HTTPException(401, "نشست پایان یافته است؛ دوباره وارد شوید.")
    if not hmac.compare_digest(session.refresh_digest, digest(data["jti"])):
        session.revoked_at = now()
        security_audit(db, "session.refresh_replay", user.id, session.sid, request)
        db.commit()
        raise HTTPException(401, "نشست پایان یافته است؛ دوباره وارد شوید.")
    jti = secrets.token_urlsafe(32)
    session.refresh_digest, session.last_used_at = digest(jti), now()
    db.commit()
    issue_cookies(response, user, session, jti)
    return {"message": "نشست تمدید شد."}


@router.post("/auth/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token") or _raw_access(request)
    if raw:
        try:
            data = decode_token(raw, "refresh" if request.cookies.get("refresh_token") else "access")
            user = db.scalar(select(User).where(User.id == int(data["sub"])).with_for_update())
            session = db.scalar(select(AccountSession).where(AccountSession.sid == data["sid"]).with_for_update())
            if user and session and session.user_id == user.id:
                session.revoked_at = now()
                security_audit(db, "session.logout", user.id, session.sid, request)
                db.commit()
        except HTTPException:
            pass
    clear_cookies(response)
    return {"message": "از حساب خارج شدید."}


@router.post("/auth/forgot-password", status_code=202, dependencies=[Depends(require_csrf)])
def forgot(data: EmailInput, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(str(data.email))
    email_throttle(db, request, email)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if valid_user(user):
        queue_token(db, "reset_password", user.email, user=user)
        db.commit()
    return GENERIC_MESSAGE


@router.post("/auth/reset-password", dependencies=[Depends(require_csrf)])
def reset(data: PasswordToken, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, "token-ip", client_ip(request), config.TOKEN_IP_LIMIT, 900)
    initial = db.scalar(select(SecurityToken).where(SecurityToken.token_hash == digest(data.token)))
    if not usable_token(initial, "reset_password"):
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    user = db.scalar(select(User).where(User.id == initial.user_id).with_for_update())
    token = db.scalar(select(SecurityToken).where(SecurityToken.id == initial.id)
                      .execution_options(populate_existing=True).with_for_update())
    if not valid_user(user) or not usable_token(token, "reset_password") or token.approved_email != user.email:
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    user.password_hash = hash_password(data.password)
    token.used_at = now()
    revoke_all(db, user)
    security_audit(db, "password.reset", user.id, str(token.id), request)
    db.commit()
    clear_cookies(response)
    return {"message": "رمز تغییر کرد؛ با رمز جدید وارد شوید."}


@router.post("/auth/verify-email", dependencies=[Depends(require_csrf)])
def verify_email(data: TokenInput, request: Request, db: Session = Depends(get_db)):
    from pilot.domain_events import account_changed, before_mutation
    throttle(db, "token-ip", client_ip(request), config.TOKEN_IP_LIMIT, 900)
    initial = db.scalar(select(SecurityToken).where(SecurityToken.token_hash == digest(data.token)))
    if not usable_token(initial, "verify_email"):
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    before_mutation(db)
    user = db.scalar(select(User).where(User.id == initial.user_id).with_for_update())
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id).with_for_update())
    token = db.scalar(select(SecurityToken).where(SecurityToken.id == initial.id)
                      .execution_options(populate_existing=True).with_for_update())
    if not usable_token(token, "verify_email") or not enrollment or enrollment.status != "eligible":
        raise HTTPException(400, "پیوند معتبر نیست یا منقضی شده است.")
    # The replacement remains private in the token until its owner confirms it.
    user.email = enrollment.email = token.approved_email
    user.email_verified = True
    revoke_all(db, user)
    token.used_at = now()
    account_changed(db, user, "email")
    db.execute(update(SecurityToken).where(SecurityToken.user_id == user.id, SecurityToken.id != token.id,
               SecurityToken.used_at.is_(None)).values(superseded_at=now()))
    security_audit(db, "email.corrected", user.id, str(token.id), request)
    db.commit()
    return {"message": "ایمیل تأیید شد؛ دوباره وارد شوید."}


@router.get("/auth/sessions")
def sessions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AccountSession).where(AccountSession.user_id == user.id,
                      AccountSession.revoked_at.is_(None), AccountSession.expires_at > now())
                      .order_by(AccountSession.created_at.desc())).all()
    return {"items": [{"sid": row.sid, "device": row.device, "created_at": row.created_at,
                       "last_used_at": row.last_used_at, "expires_at": row.expires_at,
                       "current": row.sid == request.state.sid} for row in rows]}


@router.delete("/auth/sessions", dependencies=[Depends(require_csrf)])
def revoke_sessions(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True).with_for_update())
    revoke_all(db, user)
    security_audit(db, "sessions.owner_revoke_all", user.id)
    db.commit()
    clear_cookies(response)
    return {"message": "همه نشست‌ها پایان یافت."}


@router.delete("/auth/sessions/{sid}", dependencies=[Depends(require_csrf)])
def revoke_session(sid: str, response: Response, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    session = db.scalar(select(AccountSession).where(AccountSession.sid == sid,
                        AccountSession.user_id == user.id).with_for_update())
    if not session:
        raise HTTPException(404, "نشست پیدا نشد.")
    session.revoked_at = now()
    security_audit(db, "session.owner_revoke", user.id, sid)
    db.commit()
    if sid == request.state.sid:
        clear_cookies(response)
    return {"message": "نشست پایان یافت."}
