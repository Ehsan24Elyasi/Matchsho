"""Revision-bound unanimous admission and single-winner transitions."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database import get_db
from models import Group, GroupMember, User
from pilot.domain_events import (
    OPEN_STATES,
    audit,
    aware,
    before_mutation,
    group_for,
    invalidate_proposals,
    members,
    notify,
    public_user,
)
from pilot.domain_models import CommandReceipt, Invitation, InvitationParticipant
from pilot.matching import UNAVAILABLE, MatchingContext
from pilot.security import current_user, require_csrf

router = APIRouter(prefix="/requests", tags=["invitations"])


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receiver_id: int | None = Field(None, ge=1)
    group_id: int | None = Field(None, ge=1)
    capacity: int = Field(ge=2, le=100)

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.receiver_id) == bool(self.group_id):
            raise ValueError("exactly one target is required")
        return self


def required(inv):
    return sorted(set(inv.snapshot.get("members", []) + [inv.candidate_id]))


def participants(db, inv):
    return [uid for (uid,) in db.query(InvitationParticipant.user_id).filter_by(invitation_id=inv.id)]


def bind_participants(db, inv):
    known = set(participants(db, inv))
    for uid in required(inv):
        if uid not in known:
            db.add(InvitationParticipant(invitation_id=inv.id, user_id=uid))


def snapshot(context, candidate, member_ids, capacity, group_id):
    ids = sorted(set([candidate] + member_ids))
    return {"members": sorted(member_ids), "questionnaires": {str(i): context.forms[i].revision for i in ids},
            "consents": {str(i): context.users[i].consent_version for i in ids},
            "membership_revision": context.groups[group_id].membership_revision if group_id else None,
            "group_id": group_id, "capacity": capacity,
            "pool": context.enrollments[candidate].pool, "cycle": context.enrollments[candidate].cycle}


def fresh_snapshot(db, inv):
    if inv.snapshot and inv.snapshot.get("group_id") and not inv.group_id:
        raise HTTPException(409, UNAVAILABLE)
    context = MatchingContext(db, db.get(User, inv.initiator_id))
    if inv.group_id:
        if not context.valid_group(inv.group_id) or inv.candidate_id in context.all_grouped:
            raise HTTPException(409, UNAVAILABLE)
        group = context.groups[inv.group_id]
        member_ids = context.group_members[inv.group_id]
        if inv.initiator_id not in member_ids and inv.initiator_id != inv.candidate_id:
            raise HTTPException(409, UNAVAILABLE)
        if group.capacity != inv.capacity:
            raise HTTPException(409, UNAVAILABLE)
    else:
        member_ids = [inv.target_user_id]
        if any(uid in context.all_grouped for uid in member_ids + [inv.candidate_id]):
            raise HTTPException(409, UNAVAILABLE)
    if not context.compare(inv.candidate_id, member_ids, inv.capacity):
        raise HTTPException(409, UNAVAILABLE)
    return snapshot(context, inv.candidate_id, member_ids, inv.capacity, inv.group_id)


def finish(db, inv, state, actor=None, reason=None):
    inv.status, inv.active_key, inv.reason = state, None, reason
    audit(db, actor, f"invitation.{state}", "request", inv.id, reason or "", after={"status": state})
    notify(db, required(inv), "request", "وضعیت درخواست هم‌اتاقی به‌روزرسانی شد.", "request", inv.id,
           f"invitation:{inv.id}:{state}")


def synchronize(db, inv):
    if inv.status not in OPEN_STATES:
        return
    if aware(inv.expires_at) <= datetime.now(timezone.utc):
        finish(db, inv, "expired", reason="expired")
        return
    try:
        latest = fresh_snapshot(db, inv)
    except HTTPException as exc:
        if exc.status_code not in (403, 409):
            raise
        finish(db, inv, "cancelled", reason="unavailable")
        return
    if latest != inv.snapshot and inv.status != "needs_reconfirmation":
        inv.status, inv.approvals, inv.reason = "needs_reconfirmation", [], "state_changed"
        notify(db, required(inv), "reconfirmation", "شرایط دعوت تغییر کرده است؛ بازبینی و تأیید دوباره لازم است.",
               "request", inv.id, f"revision:{inv.id}:{hashlib.sha256(json.dumps(latest, sort_keys=True).encode()).hexdigest()}")


def expire_invitations(db):
    before_mutation(db)
    for inv in db.query(Invitation).filter(Invitation.status.in_(OPEN_STATES),
                                         Invitation.expires_at <= datetime.now(timezone.utc)).all():
        finish(db, inv, "expired", reason="expired")


def dto(db, inv, viewer):
    req = required(inv)
    group = db.get(Group, inv.group_id) if inv.group_id else None
    viewer_group = group_for(db, viewer.id)
    live_members = group and (viewer.role == "admin" or inv.status in OPEN_STATES or viewer_group and viewer_group.id == group.id)
    visible_members = members(db, group.id) if live_members else db.query(User).filter(
        User.id.in_(inv.snapshot.get("members", []))).order_by(User.id).all()
    return {"id": inv.id, "initiator": public_user(db.get(User, inv.initiator_id)),
            "candidate": public_user(db.get(User, inv.candidate_id)), "capacity": inv.capacity,
            "group": {"id": group.id, "capacity": group.capacity,
                      "members": [public_user(u) for u in visible_members]} if group else None,
            "status": inv.status, "expires_at": aware(inv.expires_at), "approvals": inv.approvals,
            "required_approvals": req,
            "can_approve": inv.status == "pending" and viewer.id in req and viewer.id not in inv.approvals,
            "can_reject": inv.status in OPEN_STATES and viewer.id in req and (inv.group_id is not None or viewer.id == inv.candidate_id),
            "can_cancel": inv.status in OPEN_STATES and viewer.id == inv.initiator_id,
            "can_reconfirm": inv.status == "needs_reconfirmation" and viewer.id in req,
            "reason": inv.reason}


@router.get("")
def list_requests(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                  user=Depends(current_user), db=Depends(get_db)):
    before_mutation(db)
    query = db.query(Invitation).join(InvitationParticipant).filter(InvitationParticipant.user_id == user.id)
    total = query.count()
    rows = query.order_by(Invitation.created_at.desc(), Invitation.id.desc()).offset((page - 1) * limit).limit(limit).all()
    for inv in rows:
        synchronize(db, inv)
    result = [dto(db, inv, user) for inv in rows]
    db.commit()
    return {"items": result, "total": total, "page": page, "limit": limit}


@router.post("", dependencies=[Depends(require_csrf)])
def create_request(payload: Proposal, request: Request, user=Depends(current_user), db=Depends(get_db)):
    before_mutation(db)
    key = request.headers.get("Idempotency-Key")
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    if key:
        if len(key) > 100:
            raise HTTPException(422, "کلید درخواست معتبر نیست")
        receipt = db.query(CommandReceipt).filter_by(actor_id=user.id, action="invitation.create", key=key).first()
        if receipt:
            if receipt.payload_hash != payload_hash:
                raise HTTPException(409, "این کلید قبلاً برای درخواست دیگری استفاده شده است")
            return receipt.result
    own_group = group_for(db, user.id)
    if payload.group_id:
        if own_group:
            raise HTTPException(409, UNAVAILABLE)
        group, candidate, target = db.get(Group, payload.group_id), user.id, None
        if not group:
            raise HTTPException(404, UNAVAILABLE)
    else:
        if payload.receiver_id == user.id:
            raise HTTPException(422, UNAVAILABLE)
        group, candidate, target = own_group, payload.receiver_id, user.id
    active_key = f"group:{group.id}:candidate:{candidate}" if group else "solo:" + ":".join(map(str, sorted((user.id, candidate))))
    existing = db.query(Invitation).filter_by(active_key=active_key).first()
    if existing:
        synchronize(db, existing)
        if existing.status in OPEN_STATES:
            if existing.initiator_id == user.id and existing.capacity == payload.capacity:
                result = dto(db, existing, user)
                db.commit()
                return result
            raise HTTPException(409, "درخواست باز برای این پیشنهاد وجود دارد")
        db.flush()
    inv = Invitation(initiator_id=user.id, candidate_id=candidate, target_user_id=target,
                     group_id=group.id if group else None, capacity=payload.capacity, active_key=active_key,
                     expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    inv.snapshot = fresh_snapshot(db, inv)
    inv.approvals, inv.status = [user.id], "pending"
    db.add(inv)
    db.flush()
    bind_participants(db, inv)
    audit(db, user, "invitation.created", "request", inv.id, after={"capacity": inv.capacity, "participants": required(inv)})
    notify(db, required(inv), "request", "درخواست هم‌اتاقی تازه‌ای ثبت شد.", "request", inv.id, f"invitation:{inv.id}:created")
    result = dto(db, inv, user)
    if key:
        # JSON columns need JSON-compatible datetimes.
        from fastapi.encoders import jsonable_encoder
        db.add(CommandReceipt(actor_id=user.id, action="invitation.create", key=key,
                              payload_hash=payload_hash, result=jsonable_encoder(result)))
    db.commit()
    return result


@router.post("/{invitation_id}/{action}", dependencies=[Depends(require_csrf)])
def transition(invitation_id: int, action: str, user=Depends(current_user), db=Depends(get_db)):
    if action not in {"approve", "reject", "cancel", "reconfirm"}:
        raise HTTPException(404)
    before_mutation(db)
    inv = db.get(Invitation, invitation_id)
    if not inv or user.id not in participants(db, inv):
        raise HTTPException(404, UNAVAILABLE)
    if action == "cancel" and user.id != inv.initiator_id:
        raise HTTPException(403, UNAVAILABLE)
    if action in {"approve", "reconfirm", "reject"} and user.id not in required(inv):
        raise HTTPException(403, UNAVAILABLE)
    if action == "reject" and inv.snapshot.get("group_id") is None and user.id != inv.candidate_id:
        raise HTTPException(403, UNAVAILABLE)
    synchronize(db, inv)
    expected = {"approve": "accepted", "reject": "rejected", "cancel": "cancelled"}.get(action)
    if inv.status not in OPEN_STATES:
        result = dto(db, inv, user)
        db.commit()
        if inv.status == expected and (action != "approve" or user.id in inv.approvals):
            return result
        raise HTTPException(409, "درخواست قبلاً نهایی یا منقضی شده است")
    if action in {"reject", "cancel"}:
        finish(db, inv, expected, user, "participant_action")
    elif action == "reconfirm":
        if inv.status == "needs_reconfirmation":
            inv.snapshot, inv.approvals, inv.status, inv.reason = fresh_snapshot(db, inv), [], "pending", None
            bind_participants(db, inv)
            audit(db, user, "invitation.reconfirmed", "request", inv.id)
            notify(db, required(inv), "request", "پیشنهاد بازبینی شد؛ رأی تازهٔ همهٔ افراد لازم است.",
                   "request", inv.id, f"renewed:{inv.id}:{datetime.now(timezone.utc).isoformat()}")
    elif inv.status == "needs_reconfirmation":
        db.commit()
        raise HTTPException(409, "شرایط عوض شده است؛ ابتدا پیشنهاد را بازبینی کنید")
    else:
        inv.approvals = sorted(set(inv.approvals + [user.id]))
        if set(required(inv)) <= set(inv.approvals):
            # Recheck against current DB state inside the same domain transaction.
            if fresh_snapshot(db, inv) != inv.snapshot:
                raise HTTPException(409, UNAVAILABLE)
            if inv.group_id:
                group = db.get(Group, inv.group_id)
                db.add(GroupMember(group_id=group.id, user_id=inv.candidate_id))
                group.membership_revision += 1
            else:
                group = Group(capacity=inv.capacity, pool=inv.snapshot["pool"], cycle=inv.snapshot["cycle"],
                              membership_revision=1, reconciliation_required=False)
                db.add(group)
                db.flush()
                for uid in required(inv):
                    db.add(GroupMember(group_id=group.id, user_id=uid))
            db.flush()
            group.is_complete = len(members(db, group.id)) >= group.capacity
            finish(db, inv, "accepted", user)
            db.flush()
            invalidate_proposals(db, group_id=group.id)
            for uid in required(inv):
                invalidate_proposals(db, user_id=uid)
        else:
            notify(db, required(inv), "approval", "یک رأی برای پیشنهاد هم‌اتاقی ثبت شد.", "request", inv.id,
                   f"approval:{inv.id}:{user.id}:{hashlib.sha256(json.dumps(inv.snapshot, sort_keys=True).encode()).hexdigest()}")
    result = dto(db, inv, user)
    db.commit()
    return result
