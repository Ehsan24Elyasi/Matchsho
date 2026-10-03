"""Purpose-aware peer discovery with batched reads and bilateral scoring."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_

from database import get_db
from models import Group, GroupMember, RoomAssignment, User
from pilot import config
from pilot.domain_events import group_for, members, public_user
from pilot.domain_models import Invitation, Questionnaire
from pilot.questionnaire import VERSION, alignment
from pilot.security import current_user
from pilot.security_models import Enrollment, UserBlock

router = APIRouter(tags=["discovery"])
EXPLANATIONS = {"sleep": "ترجیحات زمان استراحت هم‌خوان است", "wake": "ترجیحات زمان بیداری هم‌خوان است",
                "cleaning": "ترجیحات نظافت هم‌خوان است", "guests": "ترجیحات مهمان هم‌خوان است",
                "noise": "ترجیحات محیط مطالعه هم‌خوان است"}
UNAVAILABLE = "این پیشنهاد در حال حاضر در دسترس نیست"


def enrollment(db, user):
    record = db.query(Enrollment).filter_by(user_id=user.id, status="eligible", cycle=config.ACTIVE_CYCLE).first()
    if not record or record.pool not in config.ALLOWED_POOLS or not user.is_active or user.account_status != "active":
        raise HTTPException(403, "عضویت شما در فهرست این دوره نیاز به بررسی مدیریت دارد")
    return record


class MatchingContext:
    """One bounded cohort load; no per-candidate SQL or silent pre-score truncation.

    The pilot deliberately caps a cohort at 2000 eligible roster entries. A
    larger deployment must profile/revise ranking instead of dropping peers.
    """
    def __init__(self, db, viewer):
        e = enrollment(db, viewer)
        rows = db.query(User, Enrollment, Questionnaire).join(Enrollment, Enrollment.user_id == User.id).join(
            Questionnaire, Questionnaire.user_id == User.id).filter(
            Enrollment.pool == e.pool, Enrollment.cycle == e.cycle, Enrollment.status == "eligible",
            User.is_active.is_(True), User.account_status == "active",
            User.email_verified.is_(True) if config.REQUIRE_EMAIL_VERIFICATION else True,
            User.discovery_consent.is_(True), Questionnaire.version == VERSION,
            Questionnaire.complete.is_(True)).order_by(User.id).limit(2001).all()
        if len(rows) > 2000:
            raise HTTPException(503, "ظرفیت پردازش این پایلوت نیاز به بررسی اپراتور دارد")
        self.users = {u.id: u for u, _, _ in rows}
        self.forms = {u.id: q for u, _, q in rows}
        self.enrollments = {u.id: en for u, en, _ in rows}
        group_rows = db.query(Group).filter_by(pool=e.pool, cycle=e.cycle).order_by(Group.id).limit(2001).all()
        if len(group_rows) > 2000:
            raise HTTPException(503, "ظرفیت پردازش این پایلوت نیاز به بررسی اپراتور دارد")
        self.groups = {g.id: g for g in group_rows}
        group_ids = list(self.groups)
        self.group_members = {gid: [] for gid in group_ids}
        self.memberships = {}
        # Include every member, including ineligible members, so none disappear
        # from the unanimous consent/eligibility calculation.
        for m in db.query(GroupMember).filter(GroupMember.group_id.in_(group_ids)).all():
            self.group_members[m.group_id].append(m.user_id)
            self.memberships[m.user_id] = m.group_id
        for ids in self.group_members.values():
            ids.sort()
        # A legacy or foreign-cohort membership must also prohibit solo discovery.
        self.all_grouped = {uid for (uid,) in db.query(GroupMember.user_id).filter(GroupMember.user_id.in_(self.users))}
        self.assigned = {gid for (gid,) in db.query(RoomAssignment.group_id).filter(RoomAssignment.group_id.in_(group_ids))}
        self.blocks = {frozenset((a, b)) for a, b in db.query(UserBlock.actor_id, UserBlock.target_id).filter(
            or_(UserBlock.actor_id.in_(self.users), UserBlock.target_id.in_(self.users)))}
        self.viewer = viewer

    def valid_group(self, group_id):
        g = self.groups.get(group_id)
        ids = self.group_members.get(group_id, [])
        return bool(g and not g.reconciliation_required and group_id not in self.assigned and ids
                    and len(ids) < g.capacity and all(uid in self.users for uid in ids)
                    and all(g.capacity in self.forms[uid].capacities for uid in ids))

    def compare(self, candidate_id, member_ids, capacity=None):
        ids = [candidate_id] + list(member_ids)
        if len(set(ids)) != len(ids) or any(uid not in self.users for uid in ids):
            return None
        capacities = set.intersection(*(set(self.forms[uid].capacities) for uid in ids))
        if capacity is not None:
            capacities &= {capacity}
        if not capacities:
            return None
        scores, reasons = [], set(EXPLANATIONS)
        for uid in member_ids:
            if frozenset((candidate_id, uid)) in self.blocks:
                return None
            score, keys = alignment(self.forms[candidate_id].answers, self.forms[uid].answers)
            if score is None:
                return None
            scores.append(score)
            reasons &= set(keys)
        if not all(self.users[uid].explanation_consent for uid in ids):
            reasons.clear()
        return {"score": min(scores), "scoring_version": "2", "score_label": "هم‌خوانی ترجیحات",
                "explanations": [EXPLANATIONS[k] for k in EXPLANATIONS if k in reasons],
                "capacities": sorted(capacities)}

    def group_dto(self, gid):
        g = self.groups[gid]
        return {"id": g.id, "capacity": g.capacity,
                "members": [public_user(self.users[uid]) for uid in self.group_members[gid]]}

    def items(self):
        viewer_id = self.viewer.id
        if viewer_id not in self.users:
            return []
        own_gid = self.memberships.get(viewer_id)
        if viewer_id in self.all_grouped and (not own_gid or not self.valid_group(own_gid)):
            return []
        result = []
        for uid in self.users:
            if uid == viewer_id or uid in self.all_grouped:
                continue
            ids = self.group_members[own_gid] if own_gid else [viewer_id]
            score = self.compare(uid, ids, self.groups[own_gid].capacity if own_gid else None)
            if score:
                result.append({"kind": "user", "id": uid, "user": public_user(self.users[uid]),
                               "group": None, "can_invite": True, **score})
        if not own_gid:
            for gid in self.groups:
                if self.valid_group(gid):
                    score = self.compare(viewer_id, self.group_members[gid], self.groups[gid].capacity)
                    if score:
                        result.append({"kind": "group", "id": gid,
                                       "user": public_user(self.users[self.group_members[gid][0]]),
                                       "group": self.group_dto(gid), "can_invite": True, **score})
        return sorted(result, key=lambda x: (-x["score"], x["kind"], x["id"]))


@router.get("/matches")
def matches(page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=50),
            user=Depends(current_user), db=Depends(get_db)):
    result = MatchingContext(db, user).items()
    return {"items": result[(page - 1) * limit:page * limit], "total": len(result), "page": page, "limit": limit}


@router.get("/profiles/{user_id}")
def profile(user_id: int, user=Depends(current_user), db=Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, UNAVAILABLE)
    if db.query(UserBlock.id).filter(or_(
        (UserBlock.actor_id == user.id) & (UserBlock.target_id == user_id),
        (UserBlock.actor_id == user_id) & (UserBlock.target_id == user.id))).first():
        raise HTTPException(404, UNAVAILABLE)
    own_group = group_for(db, user.id)
    same_group = own_group and any(u.id == target.id for u in members(db, own_group.id))
    history = db.query(Invitation.id).filter(or_(
        (Invitation.initiator_id == user.id) & (Invitation.candidate_id == user_id),
        (Invitation.initiator_id == user_id) & (Invitation.candidate_id == user.id),
        (Invitation.target_user_id == user.id) & (Invitation.candidate_id == user_id),
        (Invitation.target_user_id == user_id) & (Invitation.candidate_id == user.id))).first()
    try:
        context = MatchingContext(db, user)
        item = next((x for x in context.items() if x["user"]["id"] == user_id or
                     x["group"] and any(m["id"] == user_id for m in x["group"]["members"])), None)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        item = None
    if item:
        return {**public_user(target), **{k: v for k, v in item.items() if k not in {"id", "user", "kind"}}}
    if same_group or history or user.id == user_id:
        return {**public_user(target), "score": None, "explanations": [], "group": None,
                "capacities": [], "can_invite": False}
    raise HTTPException(404, UNAVAILABLE)
