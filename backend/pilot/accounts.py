"""Owner privacy controls and audited operator enrollment/support workflows."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Answer, GroupMember, RoomAssignment, User
from pilot import config
from pilot.domain_events import account_changed, audit, before_mutation, notify
from pilot.domain_models import (
    AllocationHistory,
    CommandReceipt,
    Departure,
    DomainAudit,
    Invitation,
    Notification,
    Questionnaire,
)
from pilot.security import (
    clear_cookies,
    current_user,
    email_throttle,
    keyed_digest,
    normalize_email,
    normalize_identity,
    now,
    owner_user,
    queue_token,
    require_admin,
    require_csrf,
    revoke_all,
    throttle,
)
from pilot.security_models import (
    AccountSession,
    DeletionLedger,
    Enrollment,
    OutboxEvent,
    SecurityToken,
    SupportCase,
    UserBlock,
)
from pilot.security_schemas import (
    CaseResolution,
    ClosureInput,
    ConsentPatch,
    CorrectionInput,
    DeliveryRetry,
    EnrollmentCorrection,
    NotificationPreference,
    ProfilePatch,
    ReportInput,
    RosterImport,
    SecurityAction,
)

router = APIRouter()
MUTATION = [Depends(require_csrf)]


def locked_user(db, user_id):
    return db.scalar(select(User).where(User.id == user_id).execution_options(populate_existing=True).with_for_update())


def enrollment_view(row):
    return {key: getattr(row, key) for key in ("id", "student_id", "email", "name", "class_name", "gender",
                                             "pool", "cycle", "status", "user_id")}


def case_view(row, operator=False):
    fields = ("id", "reference", "kind", "category", "status", "description", "resolution", "created_at", "resolved_at")
    result = {key: getattr(row, key) for key in fields}
    if operator:
        result.update(user_id=row.user_id, target_id=row.target_id, escalated=row.escalated)
    return result


def new_case(db, user, kind, category, description, target_id=None):
    case = SupportCase(reference="MS-" + secrets.token_hex(6).upper(), user_id=user.id, target_id=target_id,
                        kind=kind, category=category, description=description)
    db.add(case)
    db.flush()
    notify(db, [user.id], "support", "درخواست پشتیبانی ثبت شد؛ وضعیت در بخش پیگیری قابل مشاهده است.",
           "case", case.id, f"case:{case.id}:created")
    return case


def cancel_related(db, user_id, other_id=None):
    for invitation in db.scalars(select(Invitation).where(Invitation.status.in_(("pending", "needs_reconfirmation")))):
        ids = set(invitation.snapshot.get("members", [])) | {invitation.initiator_id, invitation.candidate_id, invitation.target_user_id}
        if user_id in ids and (other_id is None or other_id in ids):
            invitation.status, invitation.reason, invitation.active_key = "cancelled", "unavailable", None
            invitation.approvals = []
            notify(db, [i for i in ids if i], "request", "این دعوت دیگر در دسترس نیست.", "request", invitation.id,
                   f"request:{invitation.id}:unavailable")


def purge_account(db, user):
    """Irreversible erasure only after individual membership has been resolved."""
    if db.scalar(select(GroupMember.id).where(GroupMember.user_id == user.id)):
        return False
    ledger = db.get(DeletionLedger, user.id)
    if ledger is None:
        ledger = DeletionLedger(user_id=user.id, identity_digest=keyed_digest(normalize_identity(user.student_id)))
        db.add(ledger)
    cancel_related(db, user.id)
    db.execute(update(OutboxEvent).where(OutboxEvent.recipient_ref == keyed_digest(user.email.strip().lower())).values(
        encrypted_payload=None, status="cancelled", finished_at=now(), lease_owner=None, lease_until=None))
    db.execute(delete(Answer).where(Answer.user_id == user.id))
    db.execute(delete(Questionnaire).where(Questionnaire.user_id == user.id))
    db.execute(delete(AccountSession).where(AccountSession.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.execute(delete(UserBlock).where(or_(UserBlock.actor_id == user.id, UserBlock.target_id == user.id)))
    db.execute(delete(CommandReceipt).where(CommandReceipt.actor_id == user.id))
    db.execute(update(DomainAudit).where(or_(DomainAudit.actor_id == user.id,
               (DomainAudit.target_type == "user") & (DomainAudit.target_id == user.id))).values(
               reason="", before_state=None, after_state=None))
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id))
    token_condition = or_(SecurityToken.user_id == user.id,
                          SecurityToken.enrollment_id == enrollment.id if enrollment else False)
    token_ids = list(db.scalars(select(SecurityToken.id).where(token_condition)))
    if token_ids:
        db.execute(update(OutboxEvent).where(OutboxEvent.token_id.in_(token_ids)).values(
            encrypted_payload=None, status="cancelled", finished_at=now(), token_id=None, lease_owner=None, lease_until=None))
        db.execute(delete(SecurityToken).where(SecurityToken.id.in_(token_ids)))
    user.email = f"erased-{user.id}@invalid.example"
    user.student_id, user.name, user.class_name, user.gender = f"erased-{user.id}", "کاربر حذف‌شده", "", "other"
    user.password_hash = "!erased!"
    user.is_active, user.email_verified, user.account_status = False, False, "closed"
    user.discovery_consent, user.explanation_consent = False, False
    if enrollment:
        enrollment.student_id, enrollment.email, enrollment.name = user.student_id, user.email, user.name
        enrollment.class_name, enrollment.gender, enrollment.status = "", "other", "closed"
    db.execute(update(SupportCase).where(SupportCase.user_id == user.id).values(
        description="", resolution="اطلاعات شخصی طبق درخواست حذف شد.", status="resolved", resolved_at=now()))
    ledger.completed_at = now()
    return True


@router.patch("/me/profile", dependencies=MUTATION)
def profile(data: ProfilePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before_mutation(db)
    user = locked_user(db, user.id)
    if not data.name.strip() or not data.class_name.strip():
        raise HTTPException(422, "نام و رشته نمی‌توانند خالی باشند.")
    user.name, user.class_name = data.name.strip(), data.class_name.strip()
    audit(db, user, "profile.updated", "user", user.id)
    db.commit()
    return owner_user(user, db)


@router.patch("/me/consent", dependencies=MUTATION)
def consent(data: ConsentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before_mutation(db)
    user = locked_user(db, user.id)
    if (user.discovery_consent, user.explanation_consent) != (data.discovery, data.explanations):
        user.discovery_consent, user.explanation_consent = data.discovery, data.explanations
        user.consent_version += 1
        account_changed(db, user, "consent")
        audit(db, user, "consent.updated", "user", user.id,
              after={"discovery": data.discovery, "explanations": data.explanations, "version": user.consent_version})
    db.commit()
    return owner_user(user, db)


@router.patch("/me/notification-preference", dependencies=MUTATION)
def notification_preference(data: NotificationPreference, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before_mutation(db)
    user = locked_user(db, user.id)
    user.notification_email = data.email
    audit(db, user, "notifications.preference", "user", user.id, after={"email": data.email})
    db.commit()
    return owner_user(user, db)


@router.get("/me/blocks")
def blocks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(User.id, User.name).join(UserBlock, UserBlock.target_id == User.id)
                      .where(UserBlock.actor_id == user.id).limit(500)).all()
    return {"items": [{"user_id": row.id, "name": row.name} for row in rows]}


@router.post("/me/blocks/{target_id}", dependencies=MUTATION)
def block(target_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(db, "block-user", str(user.id), 30, 3600)
    before_mutation(db)
    if target_id == user.id or not db.get(User, target_id):
        raise HTTPException(404, "کاربر در دسترس نیست.")
    for user_id in sorted((user.id, target_id)):
        locked_user(db, user_id)
    existing = db.scalar(select(UserBlock.id).where(UserBlock.actor_id == user.id, UserBlock.target_id == target_id))
    if not existing:
        # Do not turn the block-list into an identity lookup for arbitrary IDs.
        # A peer must already be visible in this user's permitted context.
        from pilot.matching import profile as permitted_profile
        permitted_profile(target_id, user, db)
        db.add(UserBlock(actor_id=user.id, target_id=target_id))
    account_changed(db, user, "block")
    cancel_related(db, user.id, target_id)
    audit(db, user, "privacy.blocked", "user", target_id)
    db.commit()
    return {"message": "مسدود شد. عضویت فعلی تغییر نمی‌کند؛ برای مشکل گروه با پشتیبانی تماس بگیرید."}


@router.delete("/me/blocks/{target_id}", dependencies=MUTATION)
def unblock(target_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before_mutation(db)
    db.execute(delete(UserBlock).where(UserBlock.actor_id == user.id, UserBlock.target_id == target_id))
    audit(db, user, "privacy.unblocked", "user", target_id)
    db.commit()
    return {"message": "مسدودسازی برداشته شد."}


@router.post("/me/reports", status_code=201, dependencies=MUTATION)
def report(data: ReportInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(db, "report-user", str(user.id), 5, 3600)
    if data.target_id and (data.target_id == user.id or not db.get(User, data.target_id)):
        raise HTTPException(404, "مرجع گزارش در دسترس نیست.")
    case = new_case(db, user, "report", data.category, data.description, data.target_id)
    audit(db, user, "report.created", "case", case.id)
    db.commit()
    return case_view(case)


@router.post("/me/corrections", status_code=201, dependencies=MUTATION)
def correction(data: CorrectionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(db, "correction-user", str(user.id), 5, 3600)
    case = new_case(db, user, "correction", data.field, data.description)
    audit(db, user, "correction.requested", "case", case.id)
    db.commit()
    return case_view(case)


@router.get("/me/cases")
def cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": [case_view(row) for row in db.scalars(select(SupportCase).where(SupportCase.user_id == user.id)
                       .order_by(SupportCase.created_at.desc()).limit(100))]}


@router.post("/me/closure", status_code=202, dependencies=MUTATION)
def closure(data: ClosureInput, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before_mutation(db)
    user = locked_user(db, user.id)
    if user.role == "admin":
        raise HTTPException(409, "مدیر باید ابتدا مسئولیت عملیاتی خود را منتقل کند.")
    case = new_case(db, user, "closure", "deletion" if data.delete else "deactivation", data.reason)
    result = case_view(case)
    user.discovery_consent, user.explanation_consent, user.is_active = False, False, False
    user.account_status = "pending-closure"
    revoke_all(db, user)
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id).with_for_update())
    if enrollment:
        enrollment.status = "closed"
    if data.delete and not db.get(DeletionLedger, user.id):
        db.add(DeletionLedger(user_id=user.id, identity_digest=keyed_digest(normalize_identity(user.student_id))))
    account_changed(db, user, "closure")
    cancel_related(db, user.id)
    audit(db, user, "account.closure_requested", "user", user.id)
    db.flush()
    if not db.scalar(select(GroupMember.id).where(GroupMember.user_id == user.id)):
        if data.delete:
            purge_account(db, user)
        else:
            user.account_status = "closed"
            case.status, case.resolved_at = "resolved", now()
        result["status"] = "resolved"
    db.commit()
    clear_cookies(response)
    result["message"] = "درخواست ثبت شد و دسترسی حساب پایان یافت. شماره پیگیری را نگه دارید؛ خروج از اتاق توسط مدیر انجام می‌شود."
    return result


@router.post("/admin/roster/import", dependencies=MUTATION)
def import_roster(data: RosterImport, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    before_mutation(db)
    errors, impacts, normalized, identities, emails = [], [], [], set(), set()
    for index, row in enumerate(data.rows, 1):
        value = row.model_dump()
        value["student_id"], value["email"] = normalize_identity(row.student_id), normalize_email(str(row.email))
        problems = []
        if value["student_id"] in identities or value["email"] in emails:
            problems.append("duplicate_in_file")
        identities.add(value["student_id"])
        emails.add(value["email"])
        if row.pool not in config.ALLOWED_POOLS or row.cycle != config.ACTIVE_CYCLE:
            problems.append("invalid_pool_or_cycle")
        if db.scalar(select(Enrollment.id).where(or_(Enrollment.student_id == value["student_id"], Enrollment.email == value["email"]))):
            problems.append("existing_roster_entry")
        if db.scalar(select(DeletionLedger.user_id).where(DeletionLedger.identity_digest == keyed_digest(value["student_id"]))):
            problems.append("closed_identity_requires_operator_reconciliation")
        existing = db.scalar(select(User).where(User.student_id == value["student_id"]))
        email_owner = db.scalar(select(User).where(User.email == value["email"]))
        if email_owner and (not existing or email_owner.id != existing.id):
            problems.append("account_email_owned")
        if existing:
            bound = db.scalar(select(Enrollment.id).where(Enrollment.user_id == existing.id))
            closed = db.get(DeletionLedger, existing.id) is not None or existing.account_status != "active" or not existing.is_active
            if existing.role != "user" or closed or bound:
                problems.append("account_identity_conflict")
            elif existing.email != value["email"]:
                if existing.email_verified or email_owner:
                    problems.append("account_identity_conflict")
                else:
                    impacts.append({"row": index, "code": "legacy_email_rebind", "user_id": existing.id,
                                    "requires_confirmation": True})
                    if not data.allow_legacy_email_rebind:
                        problems.append("legacy_email_rebind_requires_confirmation")
        if problems:
            errors.append({"row": index, "codes": problems})
        normalized.append(value)
    if errors or data.dry_run:
        return {"dry_run": data.dry_run, "valid": not errors, "errors": errors, "impacts": impacts,
                "rows": len(normalized), "imported": 0}
    try:
        for value in normalized:
            db.add(Enrollment(**value))
        audit(db, admin, "roster.imported", "enrollment", None, reason=data.reason,
              after={"count": len(normalized), "reviewed_legacy_rebinds": [item["user_id"] for item in impacts]})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "فهرست هم‌زمان تغییر کرد؛ پیش‌نمایش را دوباره اجرا کنید.") from None
    return {"dry_run": False, "valid": True, "errors": [], "impacts": impacts, "rows": len(normalized), "imported": len(normalized)}


@router.get("/admin/roster")
def roster(q: str = Query("", max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
           admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    statement = select(Enrollment)
    if q:
        text = f"%{q}%"
        statement = statement.where(or_(Enrollment.name.ilike(text), Enrollment.email.ilike(text), Enrollment.student_id.ilike(text)))
    rows = db.scalars(statement.order_by(Enrollment.id).offset(offset).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    audit(db, admin, "roster.identity_access", "enrollment", None, reason="operator roster view",
          after={"record_ids": [row.id for row in rows]})
    db.commit()
    return {"items": [enrollment_view(row) for row in rows], "offset": offset, "limit": limit, "total": total}


@router.get("/admin/users")
def users(q: str = Query("", max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    statement = select(User)
    if q:
        text = f"%{q}%"
        statement = statement.where(or_(User.name.ilike(text), User.email.ilike(text), User.student_id.ilike(text)))
    rows = db.scalars(statement.order_by(User.id).offset(offset).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    # Explicit operator allowlist, deliberately excludes questionnaire and owner-only secrets.
    result = [{key: getattr(row, key) for key in ("id", "email", "name", "class_name", "student_id", "role", "account_status", "email_verified")}
              for row in rows]
    audit(db, admin, "user.identity_access", "user", None, reason="operator user view", after={"record_ids": [row.id for row in rows]})
    db.commit()
    return {"items": result, "offset": offset, "limit": limit, "total": total}


@router.get("/admin/cases")
def operator_cases(kind: str | None = None, status: str | None = None, q: str = Query("", max_length=100), offset: int = Query(0, ge=0),
                   limit: int = Query(25, ge=1, le=100), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    statement = select(SupportCase)
    if kind:
        statement = statement.where(SupportCase.kind == kind)
    if status:
        statement = statement.where(SupportCase.status == status)
    if q:
        statement = statement.where(or_(SupportCase.reference.ilike(f"%{q}%"), SupportCase.description.ilike(f"%{q}%")))
    rows = db.scalars(statement.order_by(SupportCase.created_at.desc()).offset(offset).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    audit(db, admin, "support.identity_access", "case", None, reason="operator support queue",
          after={"record_ids": [row.id for row in rows]})
    db.commit()
    return {"items": [case_view(row, True) for row in rows], "offset": offset, "limit": limit, "total": total}


@router.get("/admin/users/{user_id}")
def operator_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "کاربر پیدا نشد.")
    result = {key: getattr(user, key) for key in ("id", "email", "name", "class_name", "student_id", "role", "account_status", "email_verified")}
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id))
    member = db.scalar(select(GroupMember).where(GroupMember.user_id == user.id))
    assignment = db.scalar(select(RoomAssignment).where(RoomAssignment.group_id == member.group_id)) if member else None
    result.update(enrollment=enrollment_view(enrollment) if enrollment else None,
                  group_id=member.group_id if member else None, room_id=assignment.room_id if assignment else None)
    result["allocation_history"] = [{key: getattr(row, key) for key in ("id", "group_id", "room_id", "opened_at", "closed_at")}
        for row in db.scalars(select(AllocationHistory).where(AllocationHistory.user_id == user.id)
                              .order_by(AllocationHistory.opened_at.desc()).limit(100))]
    result["departures"] = [{key: getattr(row, key) for key in ("id", "group_id", "status", "reason", "resolution", "created_at", "resolved_at")}
        for row in db.scalars(select(Departure).where(Departure.user_id == user.id).order_by(Departure.created_at.desc()).limit(100))]
    audit(db, admin, "user.operational_record_access", "user", user.id, reason="operator identity and allocation history view")
    db.commit()
    return result


@router.patch("/admin/cases/{case_id}", dependencies=MUTATION)
def resolve_case(case_id: int, data: CaseResolution, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    before_mutation(db)
    case = db.scalar(select(SupportCase).where(SupportCase.id == case_id).with_for_update())
    if not case:
        raise HTTPException(404, "پرونده پیدا نشد.")
    if case.kind == "closure" and data.status == "resolved":
        if db.scalar(select(GroupMember.id).where(GroupMember.user_id == case.user_id)):
            raise HTTPException(409, "ابتدا خروج فردی را در بخش تخصیص تکمیل کنید.")
        user = locked_user(db, case.user_id)
        if case.category == "deletion":
            purge_account(db, user)
        else:
            user.account_status = "closed"
    previous = case.status
    case.status, case.resolution = data.status, data.reason
    case.resolved_at = now() if data.status in {"resolved", "dismissed"} else None
    audit(db, admin, "support.resolved", "case", case.id, data.reason, {"status": previous}, {"status": data.status})
    notify(db, [case.user_id], "support", "وضعیت پرونده پشتیبانی به‌روزرسانی شد.", "case", case.id,
           f"case:{case.id}:{secrets.token_hex(6)}")
    db.commit()
    return case_view(case, True)


@router.patch("/admin/enrollments/{enrollment_id}", dependencies=MUTATION)
def correct_enrollment(enrollment_id: int, data: EnrollmentCorrection, request: Request,
                       admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    before_mutation(db)
    initial = db.get(Enrollment, enrollment_id)
    if not initial:
        raise HTTPException(404, "پذیرش پیدا نشد.")
    user = locked_user(db, initial.user_id) if initial.user_id else None
    row = db.scalar(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update())
    member = db.scalar(select(GroupMember).where(GroupMember.user_id == user.id)) if user else None
    assigned = db.scalar(select(RoomAssignment).where(RoomAssignment.group_id == member.group_id)) if member else None
    value = (normalize_email(data.value) if data.field == "email" else
             normalize_identity(data.value) if data.field == "student_id" else data.value.strip())
    if data.field == "pool" and value not in config.ALLOWED_POOLS:
        raise HTTPException(422, "گروه اسکان معتبر نیست.")
    if data.field == "cycle" and value != config.ACTIVE_CYCLE:
        raise HTTPException(422, "دوره فعال معتبر نیست.")
    if data.field == "status" and value not in {"eligible", "suspended", "closed"}:
        raise HTTPException(422, "وضعیت پذیرش معتبر نیست.")
    if data.field == "email":
        try:
            value = str(TypeAdapter(EmailStr).validate_python(value))
        except ValidationError:
            raise HTTPException(422, "ایمیل معتبر نیست.") from None
    conflict = bool(member and data.field in {"pool", "cycle", "student_id", "status"})
    impact = {"user_id": row.user_id, "group_id": member.group_id if member else None,
              "assignment_id": assigned.id if assigned else None, "requires_individual_exit": conflict,
              "email_verification_required": data.field == "email" and bool(user) and config.REQUIRE_EMAIL_VERIFICATION}
    if data.dry_run:
        return {"dry_run": True, "impact": impact}
    if conflict:
        raise HTTPException(409, {"message": "ابتدا عضویت یا تخصیص را از مسیر خروج فردی حل کنید.", "impact": impact})
    if data.field in {"email", "student_id"}:
        if db.scalar(select(Enrollment.id).where(getattr(Enrollment, data.field) == value, Enrollment.id != row.id)):
            raise HTTPException(409, "شناسه با ردیف دیگری تداخل دارد.")
        if db.scalar(select(User.id).where(getattr(User, data.field) == value, User.id != (user.id if user else -1))):
            raise HTTPException(409, "شناسه با حساب دیگری تداخل دارد.")
    if data.field == "email" and user and config.REQUIRE_EMAIL_VERIFICATION:
        email_throttle(db, request, value)
        queue_token(db, "verify_email", value, user=user, lifetime_hours=24)
    else:
        setattr(row, data.field, value)
        if user and data.field == "student_id":
            user.student_id = value
        if user and data.field == "email":
            user.email, user.email_verified = value, False
            revoke_all(db, user)
        if user:
            account_changed(db, user, "enrollment")
    audit(db, admin, "enrollment.corrected", "enrollment", row.id, data.reason,
          after={"field": data.field, "verification_pending": impact["email_verification_required"]})
    db.commit()
    message = "اصلاح ثبت شد؛ تغییر ایمیل حساب پس از تأیید آدرس جدید اعمال می‌شود." if impact["email_verification_required"] else "اصلاح ثبت شد."
    return {"message": message, "impact": impact}


@router.post("/admin/users/{user_id}/security", dependencies=MUTATION)
def security_action(user_id: int, data: SecurityAction, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    before_mutation(db)
    user = locked_user(db, user_id)
    if not user:
        raise HTTPException(404, "کاربر پیدا نشد.")
    if user.role == "admin" and data.action == "suspend":
        raise HTTPException(409, "تعلیق مدیر از این مسیر مجاز نیست.")
    if data.action == "reactivate":
        if user.account_status not in {"suspended", "active"}:
            raise HTTPException(409, "حساب بسته یا در حال خروج نیازمند بررسی پذیرش مجدد است.")
        user.is_active, user.account_status = True, "active"
    else:
        revoke_all(db, user)
        if data.action == "suspend":
            user.is_active, user.account_status, user.discovery_consent = False, "suspended", False
            cancel_related(db, user.id)
    account_changed(db, user, data.action)
    audit(db, admin, "account." + data.action, "user", user.id, data.reason)
    db.commit()
    return {"message": "وضعیت امنیت حساب به‌روزرسانی شد.", "account_status": user.account_status}


@router.get("/admin/delivery/health")
def delivery_health(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from pilot.delivery import health
    return health(db)


@router.get("/admin/delivery")
def deliveries(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(OutboxEvent))
    rows = db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).offset(offset).limit(limit))
    return {"items": [{key: getattr(row, key) for key in ("id", "purpose", "recipient_ref", "status", "attempts",
                       "created_at", "next_attempt_at", "failure_code", "finished_at")} for row in rows],
            "offset": offset, "limit": limit, "total": total}


@router.post("/admin/delivery/{event_id}/retry", dependencies=MUTATION)
def retry_delivery(event_id: int, data: DeliveryRetry, request: Request,
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from pilot.delivery import decrypt_payload, eligibility
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update())
    if not event or event.status not in {"retry-scheduled", "terminal-failure"} or not event.encrypted_payload:
        raise HTTPException(409, "این پیام قابل تکرار نیست؛ در صورت نیاز پیوند تازه صادر شود.")
    try:
        payload = decrypt_payload(event)
    except ValueError:
        raise HTTPException(409, "محتوای پیام دیگر در دسترس نیست.") from None
    if eligibility(db, event, payload):
        raise HTTPException(409, "پیوند یا گیرنده دیگر معتبر نیست.")
    email_throttle(db, request, payload["recipient"])
    event.status, event.next_attempt_at = "pending", now() + timedelta(seconds=1)
    audit(db, admin, "delivery.retry", "outbox", event.id, reason=data.reason)
    db.commit()
    return {"message": "پیام برای تلاش مجدد در صف قرار گرفت."}
