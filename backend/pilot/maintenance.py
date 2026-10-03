"""Bounded retention jobs and mandatory erasure replay before opening a restore."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update

from database import SessionLocal
from models import AuditLog, AuthToken, GroupMember, RefreshSession, User
from pilot import config
from pilot.accounts import purge_account
from pilot.domain_events import before_mutation, notify
from pilot.domain_models import CommandReceipt, DomainAudit
from pilot.security import aware, keyed_digest, normalize_identity, now
from pilot.security_models import (
    AccountSession,
    DeletionLedger,
    Enrollment,
    OutboxEvent,
    RateBucket,
    SecurityToken,
    SupportCase,
    WorkerHeartbeat,
)


def process_closures(db):
    count = 0
    for entry in db.scalars(select(DeletionLedger).where(DeletionLedger.completed_at.is_(None))):
        user = db.get(User, entry.user_id)
        if user and purge_account(db, user):
            count += 1
    db.flush()
    for user in db.scalars(select(User).where(User.account_status == "pending-closure", User.is_active.is_(False))):
        if db.scalar(select(GroupMember.id).where(GroupMember.user_id == user.id)):
            continue
        user.account_status = "closed"
        db.execute(update(SupportCase).where(SupportCase.user_id == user.id, SupportCase.kind == "closure",
                   SupportCase.status.in_(("open", "reviewing"))).values(status="resolved", resolved_at=now(),
                   resolution="خروج فردی تکمیل و حساب غیرفعال شد."))
        count += 1
    return count


def maintenance(db):
    # The domain-wide lock is always acquired before any row-changing statement.
    from pilot.invitations import expire_invitations
    expire_invitations(db)
    counts = {"accounts_erased": process_closures(db)}
    instant = now()
    near_expiry = instant - timedelta(days=max(0, config.REPORT_RETENTION_DAYS - 3))
    for case in db.scalars(select(SupportCase).where(SupportCase.kind == "report", SupportCase.escalated.is_(False),
                          SupportCase.status.in_(("open", "reviewing")), SupportCase.created_at <= near_expiry)):
        case.escalated = True
        admins = db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))).all()
        notify(db, admins, "report-escalation", "یک گزارش باز به پایان مهلت نگهداری نزدیک است؛ فوراً بررسی شود.",
               "case", case.id, f"report:{case.id}:retention-escalation")
    result = db.execute(update(SupportCase).where(SupportCase.kind == "report",
                        SupportCase.created_at < instant - timedelta(days=config.REPORT_RETENTION_DAYS)).values(
                        description="", resolution="محتوای گزارش طبق سیاست نگهداری حذف شد.", target_id=None)
                        .execution_options(synchronize_session="fetch"))
    counts["reports_redacted"] = result.rowcount
    for model, condition in (
        (AuditLog, AuditLog.created_at < instant - timedelta(days=config.AUDIT_RETENTION_DAYS)),
        (DomainAudit, DomainAudit.created_at < instant - timedelta(days=config.AUDIT_RETENTION_DAYS)),
        (CommandReceipt, CommandReceipt.created_at < instant - timedelta(days=30)),
        (RateBucket, RateBucket.expires_at < instant),
        (WorkerHeartbeat, WorkerHeartbeat.last_seen_at < instant - timedelta(days=1)),
        (AccountSession, AccountSession.expires_at < instant - timedelta(days=1)),
        (RefreshSession, RefreshSession.expires_at < instant - timedelta(days=1)),
        (AuthToken, AuthToken.expires_at < instant - timedelta(days=30)),
        (OutboxEvent, OutboxEvent.finished_at < instant - timedelta(days=config.OUTBOX_RETENTION_DAYS)),
    ):
        counts[model.__tablename__] = db.execute(delete(model).where(condition)
                                               .execution_options(synchronize_session="fetch")).rowcount
    # A token becoming stale must erase its still-queued delivery payload as well.
    from pilot.delivery import SENDABLE, decrypt_payload, eligibility, finish
    for event in db.scalars(select(OutboxEvent).where(OutboxEvent.status.in_(SENDABLE)).with_for_update(skip_locked=True)):
        try:
            invalid = eligibility(db, event, decrypt_payload(event))
        except ValueError:
            invalid = "terminal-failure"
        if invalid:
            finish(event, invalid)
    db.execute(delete(SecurityToken).where(SecurityToken.expires_at < instant - timedelta(days=30),
               ~SecurityToken.id.in_(select(OutboxEvent.token_id).where(OutboxEvent.token_id.is_not(None)))))
    # Added in the shared domain model; only closed allocations age out.
    from pilot.domain_models import AllocationHistory
    counts["allocation_history"] = db.execute(delete(AllocationHistory).where(
        AllocationHistory.closed_at.is_not(None), AllocationHistory.closed_at < instant - timedelta(days=90))
        .execution_options(synchronize_session="fetch")).rowcount
    return counts


def export_ledger(db, path):
    payload = {"exported_at": now().isoformat(), "entries": [
        {"user_id": entry.user_id, "identity_digest": entry.identity_digest,
         "requested_at": aware(entry.requested_at).isoformat(),
         "completed_at": aware(entry.completed_at).isoformat() if entry.completed_at else None}
        for entry in db.scalars(select(DeletionLedger).order_by(DeletionLedger.user_id))]}
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return len(payload["entries"])


def replay_ledger(db, path):
    if os.getenv("NO_OUTBOUND_EMAIL", "false").lower() != "true":
        raise RuntimeError("Erasure replay requires NO_OUTBOUND_EMAIL=true")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    timestamp = datetime.fromisoformat(payload["exported_at"])
    if timestamp.tzinfo is None or now() - timestamp > timedelta(hours=1) or timestamp > now() + timedelta(minutes=5):
        raise RuntimeError("A fresh independently exported erasure ledger is required")
    before_mutation(db)
    count = 0
    for item in payload["entries"]:
        if not isinstance(item["user_id"], int) or len(item["identity_digest"]) != 64:
            raise ValueError("Invalid erasure ledger entry")
        entry = db.get(DeletionLedger, item["user_id"])
        if not entry:
            entry = DeletionLedger(user_id=item["user_id"], identity_digest=item["identity_digest"],
                                    requested_at=datetime.fromisoformat(item["requested_at"]))
            db.add(entry)
        user = db.get(User, item["user_id"])
        if user and not user.student_id.startswith("erased-") and keyed_digest(normalize_identity(user.student_id)) != item["identity_digest"]:
            raise RuntimeError("Erasure ledger identity does not match restored account")
        db.flush()
        if user:
            # Completed real-world exits may postdate the restored backup. Reconcile
            # only the erased individual's membership; preserve every other bed.
            if item.get("completed_at"):
                from pilot.domain_events import remove_member
                remove_member(db, user, None, "erasure replay after controlled restore")
                db.flush()
                if not purge_account(db, user):
                    raise RuntimeError("Erasure requires unresolved individual departure")
                count += 1
            else:
                from pilot.domain_events import account_changed
                from pilot.security import revoke_all
                user.is_active, user.discovery_consent, user.account_status = False, False, "pending-closure"
                revoke_all(db, user)
                enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id))
                if enrollment:
                    enrollment.status = "closed"
                account_changed(db, user, "closure")
        elif item.get("completed_at"):
            entry.completed_at = datetime.fromisoformat(item["completed_at"])
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--export-erasure-ledger")
    parser.add_argument("--reapply-erasure", action="store_true")
    parser.add_argument("--ledger")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.export_erasure_ledger:
            result = {"exported": export_ledger(db, args.export_erasure_ledger)}
        elif args.reapply_erasure:
            if not args.ledger:
                parser.error("--reapply-erasure requires --ledger")
            result = {"erased": replay_ledger(db, args.ledger)}
            db.commit()
        elif args.run:
            result = maintenance(db)
            db.commit()
        else:
            parser.error("Choose --run, --export-erasure-ledger or --reapply-erasure")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
