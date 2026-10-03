"""Versioned questionnaire validation and deterministic bilateral scoring."""
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import get_db
from models import Answer, Room
from pilot.domain_events import before_mutation, invalidate_proposals
from pilot.domain_models import Questionnaire
from pilot.security import current_user, require_csrf

router = APIRouter(prefix="/questionnaire", tags=["questionnaire"])
VERSION = 2
DIMENSIONS = [
    {"key": "sleep", "label": "معمولاً چه ساعتی می‌خوابید؟", "kind": "time", "required": True, "options": []},
    {"key": "wake", "label": "معمولاً چه ساعتی بیدار می‌شوید؟", "kind": "time", "required": True, "options": []},
    {"key": "cleaning", "label": "نظافت اتاق", "kind": "choice", "required": True, "options": [
        {"value": "daily", "label": "روزانه"}, {"value": "twice_weekly", "label": "دو بار در هفته"},
        {"value": "weekly", "label": "هفتگی"}, {"value": "less", "label": "کمتر از هفتگی"}]},
    {"key": "guests", "label": "آوردن مهمان", "kind": "choice", "required": True, "options": [
        {"value": "never", "label": "هیچ‌وقت"}, {"value": "monthly", "label": "ماهانه"},
        {"value": "weekly", "label": "هفتگی"}, {"value": "daily", "label": "روزانه"}]},
    {"key": "noise", "label": "محیط معمول مطالعه و استراحت", "kind": "choice", "required": True, "options": [
        {"value": "quiet", "label": "ساکت"}, {"value": "headphones", "label": "استفاده از هدفون"},
        {"value": "conversation", "label": "گفت‌وگو"}, {"value": "music", "label": "موسیقی با صدای بلند"}]},
    {"key": "tobacco", "label": "مصرف دخانیات (اختیاری و خصوصی)", "kind": "choice", "required": False, "options": [
        {"value": "never", "label": "مصرف نمی‌کنم"}, {"value": "outside", "label": "فقط بیرون"},
        {"value": "inside", "label": "داخل اتاق"}]},
]


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = VERSION
    answers: dict = Field(default_factory=dict)
    capacities: list[int] = Field(default_factory=list, max_length=20)


def minute(value):
    try:
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError
        hour, minutes = map(int, value.split(":"))
        if not (0 <= hour < 24 and minutes in (0, 15, 30, 45)):
            raise ValueError
        return hour * 60 + minutes
    except (ValueError, TypeError):
        raise HTTPException(422, "ساعت باید به شکل HH:MM و در فاصلهٔ ۱۵دقیقه باشد") from None


def validate_answers(payload, complete=True):
    if payload.version != VERSION:
        raise HTTPException(409, "نسخهٔ پرسشنامه تغییر کرده است؛ پاسخ‌ها را بازبینی کنید")
    if len(payload.answers) > len(DIMENSIONS) or set(payload.answers) - {d["key"] for d in DIMENSIONS}:
        raise HTTPException(422, "سؤال ناشناخته است")
    for dim in DIMENSIONS:
        answer = payload.answers.get(dim["key"])
        if not answer:
            if complete and dim["required"]:
                raise HTTPException(422, f"پاسخ {dim['label']} لازم است")
            continue
        if not isinstance(answer, dict) or set(answer) - {"own", "accepted", "importance", "hard"}:
            raise HTTPException(422, f"ساختار پاسخ {dim['key']} معتبر نیست")
        if type(answer.get("importance", 2)) is not int or answer.get("importance", 2) not in (1, 2, 3) or not isinstance(answer.get("hard", False), bool):
            raise HTTPException(422, "اهمیت و محدودیت قطعی معتبر نیست")
        accepted = answer.get("accepted")
        if not isinstance(accepted, list) or not accepted:
            raise HTTPException(422, "بازه یا گزینه‌های قابل‌پذیرش را مشخص کنید")
        own = answer.get("own")
        if dim["kind"] == "time":
            minute(own)
            if len(accepted) != 2:
                raise HTTPException(422, "شروع و پایان بازهٔ قابل‌پذیرش لازم است")
            for value in accepted:
                minute(value)
        else:
            options = {o["value"] for o in dim["options"]}
            if own is not None and not isinstance(own, str):
                raise HTTPException(422, "گزینهٔ رفتار باید متن یکی از گزینه‌های مشخص‌شده باشد")
            if own not in options and (dim["required"] or own is not None):
                raise HTTPException(422, "گزینهٔ رفتار معتبر نیست")
            if len(accepted) > len(options) or any(not isinstance(value, str) or value not in options for value in accepted):
                raise HTTPException(422, "گزینهٔ قابل‌پذیرش معتبر نیست")
    if complete and not payload.capacities:
        raise HTTPException(422, "حداقل یک ظرفیت اتاق را انتخاب کنید")
    if any(type(x) is not int or not 2 <= x <= 100 for x in payload.capacities):
        raise HTTPException(422, "ظرفیت معتبر نیست")


def accepts(dim, preference, own):
    if own is None:
        return None
    values = preference["accepted"]
    if dim["kind"] == "time":
        start, end, value = minute(values[0]), minute(values[1]), minute(own)
        return start <= value <= end if start <= end else value >= start or value <= end
    return own in values


def alignment(left, right):
    total = satisfied = 0
    explanations = []
    for dim in DIMENSIONS:
        both = []
        for a, b in ((left, right), (right, left)):
            pref = a.get(dim["key"])
            other = b.get(dim["key"], {})
            if not pref:
                continue
            result = accepts(dim, pref, other.get("own"))
            if pref.get("hard", False) and result is not True:
                return None, []
            if result is None:
                continue
            weight = pref.get("importance", 2)
            total += weight
            satisfied += weight if result else 0
            both.append(result)
        if dim["key"] != "tobacco" and len(both) == 2 and all(both):
            explanations.append(dim["key"])
    score = int((Decimal(100) * satisfied / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total else 0
    return score, explanations


def response(record):
    return {"version": VERSION, "revision": record.revision if record else 0,
            "answers": record.answers if record else {}, "capacities": record.capacities if record else [],
            "complete": bool(record and record.complete and record.version == VERSION)}


@router.get("/schema")
def schema(user=Depends(current_user), db=Depends(get_db)):
    from pilot.matching import enrollment
    e = enrollment(db, user)
    rooms = db.query(Room.capacity).filter_by(pool=e.pool, cycle=e.cycle, reconciliation_required=False).distinct()
    return {"version": VERSION, "scoring_version": "2", "dimensions": DIMENSIONS,
            "capacities": sorted(cap for (cap,) in rooms if cap >= 2)}


@router.get("/me")
def get_answers(user=Depends(current_user), db=Depends(get_db)):
    return response(db.get(Questionnaire, user.id))


@router.put("/me", dependencies=[Depends(require_csrf)])
def put_answers(payload: Submission, user=Depends(current_user), db=Depends(get_db)):
    from pilot.matching import enrollment
    before_mutation(db)
    e = enrollment(db, user)
    validate_answers(payload)
    available = {cap for (cap,) in db.query(Room.capacity).filter_by(pool=e.pool, cycle=e.cycle, reconciliation_required=False)}
    if not set(payload.capacities) <= available:
        raise HTTPException(422, "ظرفیت انتخاب‌شده در فهرست اتاق‌های مجاز نیست")
    q = db.get(Questionnaire, user.id) or Questionnaire(user_id=user.id, revision=0)
    q.version, q.answers, q.capacities = VERSION, payload.answers, sorted(set(payload.capacities))
    q.complete, q.draft, q.revision = True, None, q.revision + 1
    db.add(q)
    # V1 importance scales are neither behavior nor needed after a valid v2
    # replacement, especially the retired sensitive question.
    db.query(Answer).filter_by(user_id=user.id).delete(synchronize_session=False)
    invalidate_proposals(db, user_id=user.id, reason="questionnaire_changed")
    db.commit()
    return response(q)


@router.get("/draft")
def get_draft(user=Depends(current_user), db=Depends(get_db)):
    q = db.get(Questionnaire, user.id)
    return q.draft if q and q.draft else {"version": VERSION, "answers": {}, "capacities": []}


@router.put("/draft", dependencies=[Depends(require_csrf)])
def save_draft(payload: Submission, user=Depends(current_user), db=Depends(get_db)):
    before_mutation(db)
    if payload.version != VERSION or len(str(payload.model_dump())) > 16000:
        raise HTTPException(422, "نسخه یا حجم پیش‌نویس معتبر نیست")
    q = db.get(Questionnaire, user.id) or Questionnaire(user_id=user.id)
    q.draft = payload.model_dump()
    db.add(q)
    db.commit()
    return q.draft
