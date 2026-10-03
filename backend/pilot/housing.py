"""Group planning, reviewed room allocation and individual departures."""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_

from database import get_db
from models import Group, GroupMember, Room, RoomAssignment, User
from pilot import config
from pilot.commands import Command
from pilot.domain_events import (
    assigned,
    audit,
    before_mutation,
    group_for,
    invalidate_proposals,
    members,
    notify,
    occupancy,
    public_user,
    remove_member,
)
from pilot.domain_models import AllocationHistory, Departure, DomainAudit, Notification
from pilot.matching import enrollment
from pilot.security import current_user, require_admin, require_csrf

router = APIRouter(tags=["housing"])


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=1000)


class Allocation(Reason):
    room_id: int = Field(ge=1)


class Decision(Reason):
    decision: str = Field(pattern="^(approved|rejected)$")


class RoomInput(Reason):
    number: str = Field(min_length=1, max_length=20)
    dormitory: str = Field(min_length=1, max_length=100)
    capacity: int = Field(ge=2, le=100)
    pool: str = Field(min_length=1, max_length=100)
    cycle: str = Field(min_length=1, max_length=100)


class GroupPolicy(Reason):
    pool: str = Field(min_length=1, max_length=100)
    cycle: str = Field(min_length=1, max_length=100)
    capacity: int = Field(ge=2, le=100)


def page_of(query, serialize, page, limit):
    return {"items": [serialize(x) for x in query.offset((page - 1) * limit).limit(limit).all()],
            "total": query.count(), "page": page, "limit": limit}


def room_dto(db, room):
    count = occupancy(db, room.id)
    occupied = db.query(RoomAssignment.id).filter_by(room_id=room.id).first() is not None
    return {"id": room.id, "number": room.number, "dormitory": room.dormitory, "capacity": room.capacity,
            "current_occupancy": count, "pool": room.pool, "cycle": room.cycle,
            "reconciliation_required": room.reconciliation_required or count != room.current_occupancy,
            "available": not occupied and not room.reconciliation_required and room.cycle == config.ACTIVE_CYCLE}


def group_dto(db, group, viewer=None):
    assignment = assigned(db, group.id)
    room = db.get(Room, assignment.room_id) if assignment else None
    departure = db.query(Departure).filter_by(user_id=viewer.id).order_by(Departure.id.desc()).first() if viewer else None
    return {"id": group.id, "capacity": group.capacity, "membership_revision": group.membership_revision,
            "pool": group.pool, "cycle": group.cycle, "reconciliation_required": group.reconciliation_required,
            "members": [public_user(u) for u in members(db, group.id)],
            "room": room_dto(db, room) if room else None, "departure": departure_dto(db, departure) if departure else None}


def departure_dto(db, departure):
    user = db.get(User, departure.user_id) if departure.user_id else None
    return {"id": departure.id, "user": public_user(user) if user else None, "group_id": departure.group_id,
            "status": departure.status, "reason": departure.reason, "resolution": departure.resolution,
            "created_at": departure.created_at, "resolved_at": departure.resolved_at}


@router.get("/group/me")
def my_group(user=Depends(current_user), db=Depends(get_db)):
    group = group_for(db, user.id)
    if not group:
        raise HTTPException(404, "هنوز عضو گروهی نیستید")
    return group_dto(db, group, user)


@router.delete("/group/me", dependencies=[Depends(require_csrf)])
def leave_group(user=Depends(current_user), db=Depends(get_db)):
    before_mutation(db)
    group = group_for(db, user.id)
    if group and assigned(db, group.id):
        raise HTTPException(409, "برای خروج از اتاق تخصیص‌یافته درخواست خروج ثبت کنید")
    remove_member(db, user, user, "خروج به درخواست عضو")
    db.commit()
    return {"message": "خروج از گروه ثبت شد"}


@router.post("/group/me/departure", dependencies=[Depends(require_csrf)])
def request_departure(payload: Reason, request: Request, user=Depends(current_user), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, user, "departure.request", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    group = group_for(db, user.id)
    if not group or not assigned(db, group.id):
        raise HTTPException(409, "تخصیص فعالی برای درخواست خروج وجود ندارد")
    dep = db.query(Departure).filter_by(active_key=f"user:{user.id}").first()
    if not dep:
        dep = Departure(user_id=user.id, group_id=group.id, reason=payload.reason, active_key=f"user:{user.id}")
        db.add(dep)
        db.flush()
        audit(db, user, "departure.requested", "departure", dep.id, payload.reason)
        notify(db, [user.id], "departure", "درخواست خروج برای بررسی مدیریت ثبت شد.", "departure", dep.id, f"departure:{dep.id}:created")
    result = command.finish(departure_dto(db, dep))
    db.commit()
    return result


@router.get("/departures/me")
def own_departures(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                  user=Depends(current_user), db=Depends(get_db)):
    return page_of(db.query(Departure).filter_by(user_id=user.id).order_by(Departure.id.desc()),
                   lambda x: departure_dto(db, x), page, limit)


@router.get("/rooms")
def rooms(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), user=Depends(current_user), db=Depends(get_db)):
    e = enrollment(db, user)
    return page_of(db.query(Room).filter_by(pool=e.pool, cycle=e.cycle).order_by(Room.id), lambda x: room_dto(db, x), page, limit)


@router.get("/notifications")
def notifications(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), user=Depends(current_user), db=Depends(get_db)):
    query = db.query(Notification).filter_by(user_id=user.id)
    result = page_of(query.order_by(Notification.id.desc()), lambda n: {"id": n.id, "kind": n.kind, "message": n.message,
         "entity_type": n.entity_type, "entity_id": n.entity_id, "read": n.read, "created_at": n.created_at}, page, limit)
    result["unread"] = query.filter_by(read=False).count()
    return result


@router.post("/notifications/{notification_id}/read", dependencies=[Depends(require_csrf)])
def mark_read(notification_id: int, user=Depends(current_user), db=Depends(get_db)):
    n = db.query(Notification).filter_by(id=notification_id, user_id=user.id).first()
    if not n:
        raise HTTPException(404)
    n.read = True
    db.commit()
    return {"id": n.id, "read": True}


@router.get("/admin/rooms")
def admin_rooms(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), q: str = Query("", max_length=100),
                admin=Depends(require_admin), db=Depends(get_db)):
    query = db.query(Room)
    if q:
        query = query.filter(or_(Room.number.contains(q, autoescape=True), Room.dormitory.contains(q, autoescape=True)))
    return page_of(query.order_by(Room.id), lambda x: room_dto(db, x), page, limit)


def allocation_issues(db, group, room=None):
    issues = []
    users = members(db, group.id)
    if group.reconciliation_required or group.pool not in config.ALLOWED_POOLS or group.cycle != config.ACTIVE_CYCLE:
        issues.append("سیاست گروه نیازمند بازبینی است")
    if not users or len(users) > group.capacity:
        issues.append("تعداد اعضا با ظرفیت گروه سازگار نیست")
    for member in users:
        try:
            e = enrollment(db, member)
            if (config.REQUIRE_EMAIL_VERIFICATION and not member.email_verified) or (e.pool, e.cycle) != (group.pool, group.cycle):
                issues.append(f"عضو {member.id} شرایط تأییدشدهٔ این گروه را ندارد")
        except HTTPException:
            issues.append(f"عضو {member.id} در این دوره واجد شرایط نیست")
    if room:
        if room.reconciliation_required or (room.pool, room.cycle) != (group.pool, group.cycle):
            issues.append("سیاست اتاق با گروه سازگار نیست یا بازبینی نشده است")
        if room.capacity != group.capacity:
            issues.append("ظرفیت فیزیکی اتاق باید با ظرفیت مورد توافق گروه برابر باشد")
        if db.query(RoomAssignment.id).filter(RoomAssignment.room_id == room.id, RoomAssignment.group_id != group.id).first():
            issues.append("این اتاق به گروه دیگری تخصیص یافته است")
        if room.current_occupancy != occupancy(db, room.id):
            issues.append("شمارش ظرفیت اتاق نیازمند تطبیق اپراتور است")
    return issues


@router.get("/admin/groups")
def admin_groups(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                 q: str = Query("", max_length=100), admin=Depends(require_admin), db=Depends(get_db)):
    def row(g):
        issues = allocation_issues(db, g)
        return {**group_dto(db, g), "allocation_issues": issues, "eligible": not issues}
    query = db.query(Group)
    if q:
        group_ids = db.query(GroupMember.group_id).join(User, User.id == GroupMember.user_id).filter(User.name.contains(q, autoescape=True))
        query = query.filter(or_(Group.id == int(q) if q.isascii() and q.isdigit() else False, Group.id.in_(group_ids)))
    return page_of(query.order_by(Group.id), row, page, limit)


def validate_policy(pool, cycle):
    if pool not in config.ALLOWED_POOLS or cycle != config.ACTIVE_CYCLE:
        raise HTTPException(422, "pool و دوره باید در پیکربندی پایلوت فعال باشند")


@router.post("/admin/rooms", dependencies=[Depends(require_csrf)])
def create_room(payload: RoomInput, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, "room.create", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    validate_policy(payload.pool, payload.cycle)
    room = Room(**payload.model_dump(exclude={"reason"}), reconciliation_required=False)
    db.add(room)
    db.flush()
    audit(db, admin, "room.created", "room", room.id, payload.reason, after=room_dto(db, room), request_id=request.state.request_id)
    result = command.finish(room_dto(db, room))
    db.commit()
    return result


@router.patch("/admin/rooms/{room_id}", dependencies=[Depends(require_csrf)])
def edit_room(room_id: int, payload: RoomInput, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, f"room.edit:{room_id}", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(404)
    validate_policy(payload.pool, payload.cycle)
    before = room_dto(db, room)
    groups = db.query(Group).join(RoomAssignment).filter(RoomAssignment.room_id == room.id).all()
    if len(groups) > 1 or occupancy(db, room.id) > payload.capacity:
        raise HTTPException(409, "ابتدا تخصیص‌های ناسازگار را با انتقال یا خروج بررسی‌شده اصلاح کنید")
    for group in groups:
        if allocation_issues(db, group) or (group.capacity, group.pool, group.cycle) != (payload.capacity, payload.pool, payload.cycle):
            raise HTTPException(409, "تغییر سیاست با تخصیص جاری سازگار نیست؛ ابتدا گروه را بازبینی کنید")
    for key, value in payload.model_dump(exclude={"reason"}).items():
        setattr(room, key, value)
    room.current_occupancy = occupancy(db, room.id)
    room.reconciliation_required = False
    audit(db, admin, "room.policy", "room", room.id, payload.reason, before, room_dto(db, room), request.state.request_id)
    result = command.finish(room_dto(db, room))
    db.commit()
    return result


@router.post("/admin/groups/{group_id}/reconcile", dependencies=[Depends(require_csrf)])
def reconcile_group(group_id: int, payload: GroupPolicy, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404)
    validate_policy(payload.pool, payload.cycle)
    before = group_dto(db, group)
    if payload.capacity != group.capacity:
        raise HTTPException(409, "ظرفیت توافق‌شده با تصمیم یک‌طرفهٔ مدیر تغییر نمی‌کند")
    for u in members(db, group.id):
        e = enrollment(db, u)
        if (config.REQUIRE_EMAIL_VERIFICATION and not u.email_verified) or (e.pool, e.cycle) != (payload.pool, payload.cycle):
            raise HTTPException(409, "ابتدا عضویت و هویت همهٔ اعضا را بازبینی کنید")
    group.pool, group.cycle, group.reconciliation_required = payload.pool, payload.cycle, False
    group.membership_revision += 1
    invalidate_proposals(db, group_id=group.id)
    audit(db, admin, "group.reconciled", "group", group.id, payload.reason, before, group_dto(db, group))
    result = group_dto(db, group)
    db.commit()
    return result


def close_history(db, group_id):
    for h in db.query(AllocationHistory).filter_by(group_id=group_id, closed_at=None):
        h.closed_at = datetime.now(timezone.utc)


@router.post("/admin/groups/{group_id}/allocation", dependencies=[Depends(require_csrf)])
def allocate(group_id: int, payload: Allocation, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, f"allocation.set:{group_id}", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    group, room = db.get(Group, group_id), db.get(Room, payload.room_id)
    if not group or not room:
        raise HTTPException(404)
    issues = allocation_issues(db, group, room)
    if issues:
        raise HTTPException(409, "؛ ".join(issues))
    assignment = assigned(db, group.id)
    if assignment and assignment.room_id == room.id:
        result = command.finish(group_dto(db, group))
        db.commit()
        return result
    old_room = db.get(Room, assignment.room_id) if assignment else None
    if old_room and (old_room.reconciliation_required or old_room.current_occupancy != occupancy(db, old_room.id)):
        # Moving out is the reviewed way to resolve legacy sharing; preserve all
        # other memberships, recompute both counters from truth below.
        if occupancy(db, old_room.id) > old_room.capacity:
            raise HTTPException(409, "اتاق مبدأ بیش از ظرفیت است؛ ابتدا خروج بررسی‌شده لازم است")
    before = {"group": group_dto(db, group), "destination": room_dto(db, room)}
    close_history(db, group.id)
    if assignment:
        assignment.room_id = room.id
    else:
        db.add(RoomAssignment(group_id=group.id, room_id=room.id))
    users = members(db, group.id)
    for u in users:
        db.add(AllocationHistory(user_id=u.id, group_id=group.id, room_id=room.id))
    db.flush()
    room.current_occupancy = occupancy(db, room.id)
    if old_room:
        old_room.current_occupancy = occupancy(db, old_room.id)
    invalidate_proposals(db, group_id=group.id, reason="allocated")
    audit(db, admin, "allocation.moved" if old_room else "allocation.created", "group", group.id, payload.reason,
          before, {"group": group_dto(db, group), "previous_room": room_dto(db, old_room) if old_room else None}, request.state.request_id)
    notify(db, [u.id for u in users], "allocation", "تخصیص اتاق گروه شما ثبت شد؛ جزئیات را در صفحهٔ گروه ببینید.",
           "group", group.id, f"allocation:{group.id}:{room.id}:{datetime.now(timezone.utc).isoformat()}")
    result = command.finish(group_dto(db, group))
    db.commit()
    return result


@router.delete("/admin/groups/{group_id}/allocation", dependencies=[Depends(require_csrf)])
def unassign(group_id: int, payload: Reason, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, f"allocation.remove:{group_id}", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404)
    assignment = assigned(db, group.id)
    if assignment:
        room = db.get(Room, assignment.room_id)
        before = group_dto(db, group)
        close_history(db, group.id)
        db.delete(assignment)
        db.flush()
        room.current_occupancy = occupancy(db, room.id)
        audit(db, admin, "allocation.removed", "group", group.id, payload.reason, before, group_dto(db, group))
        notify(db, [u.id for u in members(db, group.id)], "allocation", "تخصیص اتاق با تصمیم مدیریت لغو شد.",
               "group", group.id, f"unassign:{group.id}:{datetime.now(timezone.utc).isoformat()}")
    result = command.finish(group_dto(db, group))
    db.commit()
    return result


@router.get("/admin/departures")
def departures(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), q: str = Query("", max_length=100),
               admin=Depends(require_admin), db=Depends(get_db)):
    query = db.query(Departure)
    if q:
        query = query.filter(or_(Departure.status == q, Departure.user_id.in_(db.query(User.id).filter(User.name.contains(q, autoescape=True)))))
    return page_of(query.order_by(Departure.id.desc()), lambda d: departure_dto(db, d), page, limit)


@router.post("/admin/departures/{departure_id}/resolve", dependencies=[Depends(require_csrf)])
def resolve_departure(departure_id: int, payload: Decision, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, f"departure.resolve:{departure_id}", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    dep = db.get(Departure, departure_id)
    if not dep:
        raise HTTPException(404)
    if dep.status != "pending":
        if dep.status == payload.decision:
            return departure_dto(db, dep)
        raise HTTPException(409, "این درخواست قبلاً تصمیم‌گیری شده است")
    user = db.get(User, dep.user_id)
    group = group_for(db, user.id) if user else None
    if payload.decision == "approved":
        if not group or group.id != dep.group_id:
            raise HTTPException(409, "عضویت فعلی با درخواست خروج یکسان نیست؛ وضعیت را بازبینی کنید")
        remove_member(db, user, admin, payload.reason)
    dep.status, dep.resolution, dep.active_key = payload.decision, payload.reason, None
    dep.resolved_at = datetime.now(timezone.utc)
    audit(db, admin, "departure.resolved", "departure", dep.id, payload.reason, after={"status": dep.status})
    if user:
        notify(db, [user.id], "departure", "نتیجهٔ درخواست خروج ثبت شد.", "departure", dep.id, f"departure:{dep.id}:{dep.status}")
    result = command.finish(departure_dto(db, dep))
    db.commit()
    return result


@router.delete("/admin/groups/{group_id}/members/{user_id}", dependencies=[Depends(require_csrf)])
def remove_group_member(group_id: int, user_id: int, payload: Reason, request: Request, admin=Depends(require_admin), db=Depends(get_db)):
    before_mutation(db)
    command = Command(db, admin, f"member.remove:{group_id}:{user_id}", payload.model_dump(), request)
    if command.cached is not None:
        return command.cached
    member = db.query(GroupMember).filter_by(group_id=group_id, user_id=user_id).first()
    if member:
        remove_member(db, db.get(User, user_id), admin, payload.reason)
        dep = db.query(Departure).filter_by(user_id=user_id, status="pending").first()
        if dep:
            dep.status, dep.active_key, dep.resolution, dep.resolved_at = "approved", None, payload.reason, datetime.now(timezone.utc)
    result = command.finish({"message": "وضعیت عضویت به‌روزرسانی شد"})
    db.commit()
    return result


@router.get("/admin/audit")
def audit_list(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), q: str = Query("", max_length=100),
               admin=Depends(require_admin), db=Depends(get_db)):
    query = db.query(DomainAudit)
    if q:
        query = query.filter(or_(DomainAudit.action.contains(q, autoescape=True), DomainAudit.reason.contains(q, autoescape=True)))
    return page_of(query.order_by(DomainAudit.id.desc()), lambda a: {"id": a.id, "actor_id": a.actor_id,
        "action": a.action, "target_type": a.target_type, "target_id": a.target_id, "reason": a.reason,
        "before": a.before_state, "after": a.after_state, "created_at": a.created_at, "request_id": a.request_id}, page, limit)


def safe_csv(value):
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or value[:1] in ("\t", "\r", "\n") else value


@router.get("/admin/export")
def export(resource: str = Query(pattern="^(groups|rooms)$"), admin=Depends(require_admin), db=Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    if resource == "rooms":
        writer.writerow(["id", "dormitory", "number", "capacity", "occupancy", "pool", "cycle"])
        for room in db.query(Room).order_by(Room.id).yield_per(100):
            writer.writerow(map(safe_csv, [room.id, room.dormitory, room.number, room.capacity, occupancy(db, room.id), room.pool, room.cycle]))
    else:
        writer.writerow(["id", "capacity", "member_count", "room_id", "pool", "cycle"])
        for group in db.query(Group).order_by(Group.id).yield_per(100):
            assignment = assigned(db, group.id)
            writer.writerow(map(safe_csv, [group.id, group.capacity, len(members(db, group.id)),
                                          assignment.room_id if assignment else None, group.pool, group.cycle]))
    audit(db, admin, "export.created", resource, None, "خروجی حداقلی اپراتور")
    db.commit()
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{resource}.csv"'})
