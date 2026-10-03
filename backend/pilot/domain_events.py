"""Shared transaction boundary for the small pilot's domain writes.

The advisory lock precedes row locks. It is transaction-scoped, shared by replicas,
and deliberately serializes the pilot's short membership/eligibility mutations.
Authentication hashing and SMTP do not run inside this lock.
"""
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import text

from models import Group, GroupMember, Room, RoomAssignment, User
from pilot.domain_models import AllocationHistory, Departure, DomainAudit, Invitation, Notification

DOMAIN_LOCK_KEY = 7364202610
OPEN_STATES = ("pending", "needs_reconfirmation")
request_context = ContextVar("request_id", default=None)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def before_mutation(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DOMAIN_LOCK_KEY})
    # Invalidate identity-map state loaded before waiting on another transaction.
    db.expire_all()


def public_user(user):
    return {"id": user.id, "name": user.name, "class_name": user.class_name}


def audit(db, actor, action, target_type, target_id, reason="", before=None, after=None, request_id=None):
    db.add(DomainAudit(actor_id=actor.id if actor else None, action=action,
                       target_type=target_type, target_id=target_id, reason=reason,
                       before_state=before, after_state=after, request_id=request_id or request_context.get()))


def notify(db, users, kind, message, entity_type, entity_id, event_key):
    for user_id in sorted(set(users)):
        exists = db.query(Notification.id).filter_by(user_id=user_id, event_key=event_key).first()
        if not exists:
            db.add(Notification(user_id=user_id, kind=kind, message=message,
                                entity_type=entity_type, entity_id=entity_id, event_key=event_key))
            user = db.get(User, user_id)
            if user and user.notification_email and user.is_active and user.email_verified and user.account_status == "active":
                from pilot.delivery import enqueue
                enqueue(db, user.email, "اعلان مچ‌شو", message + "\nبرای مشاهدهٔ وضعیت جاری وارد مچ‌شو شوید.",
                        event_key=f"notice:{user_id}:{event_key}")
    db.flush()


def group_for(db, user_id):
    member = db.query(GroupMember).filter_by(user_id=user_id).first()
    return db.get(Group, member.group_id) if member else None


def members(db, group_id):
    return db.query(User).join(GroupMember, GroupMember.user_id == User.id).filter(
        GroupMember.group_id == group_id).order_by(User.id).all()


def assigned(db, group_id):
    return db.query(RoomAssignment).filter_by(group_id=group_id).first()


def occupancy(db, room_id):
    return db.query(GroupMember).join(RoomAssignment, RoomAssignment.group_id == GroupMember.group_id).filter(
        RoomAssignment.room_id == room_id).count()


def invalidate_proposals(db, user_id=None, group_id=None, reason="state_changed"):
    for inv in db.query(Invitation).filter(Invitation.status.in_(OPEN_STATES)).all():
        ids = inv.snapshot.get("members", []) + [inv.candidate_id, inv.initiator_id]
        if (user_id is not None and user_id in ids) or (group_id is not None and inv.group_id == group_id):
            inv.status = "needs_reconfirmation"
            inv.approvals = []
            inv.reason = reason
            notify(db, ids, "reconfirmation", "شرایط دعوت تغییر کرده است؛ تأیید دوباره لازم است.",
                   "request", inv.id, f"reconfirm:{inv.id}:{datetime.now(timezone.utc).isoformat()}")


def remove_member(db, user, actor, reason):
    group = group_for(db, user.id)
    if not group:
        return
    before_ids = [u.id for u in members(db, group.id)]
    assignment = assigned(db, group.id)
    room = db.get(Room, assignment.room_id) if assignment else None
    before = {"members": before_ids, "room_id": room.id if room else None,
              "occupancy": occupancy(db, room.id) if room else None}
    db.query(GroupMember).filter_by(user_id=user.id).delete(synchronize_session=False)
    for history in db.query(AllocationHistory).filter_by(user_id=user.id, group_id=group.id, closed_at=None):
        history.closed_at = datetime.now(timezone.utc)
    db.flush()
    group.membership_revision += 1
    remaining = members(db, group.id)
    group.is_complete = len(remaining) >= group.capacity
    invalidate_proposals(db, group_id=group.id)
    if not remaining:
        if assignment:
            db.delete(assignment)
        db.flush()
        db.delete(group)
    db.flush()
    if room:
        room.current_occupancy = occupancy(db, room.id)
    audit(db, actor, "member.removed", "group", group.id, reason, before,
          {"members": [u.id for u in remaining], "occupancy": room.current_occupancy if room else None})
    notify(db, before_ids, "departure", "وضعیت عضویت گروه به‌روزرسانی شد.", "group", group.id,
           f"departure:{group.id}:{user.id}:{group.membership_revision}")


def account_changed(db, user, event):
    """Call after account writes, with before_mutation acquired before row locks."""
    invalidate_proposals(db, user_id=user.id, reason="account_changed")
    if event in {"closure", "delete", "deactivate", "pending_closure"} or user.account_status in {
        "pending_closure", "pending-closure", "pending_exit", "closed", "deleted", "deactivated"
    }:
        group = group_for(db, user.id)
        if group and assigned(db, group.id):
            if not db.query(Departure).filter_by(active_key=f"user:{user.id}").first():
                db.add(Departure(user_id=user.id, group_id=group.id, active_key=f"user:{user.id}",
                                 reason="درخواست بستن حساب"))
        elif group:
            remove_member(db, user, user, "بستن حساب")
