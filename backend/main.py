from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload
from database import Base, engine, get_db, SessionLocal
from models import (
    User as UserModel, Room as RoomModel, Group as GroupModel,
    GroupMember as GroupMemberModel, RoommateRequest as RoommateRequestModel,
    Question as QuestionModel, Answer as AnswerModel
)
from schemas import (
    UserCreate, User, Room, RoomCreate, RoomUpdate,
    GroupSchema, GroupMemberSchema,
    RoommateRequestCreate, RoommateRequestSchema,
    Question, Answer, AnswerBase,
    LoginRequest, MatchResponse, AdminLoginRequest
)
from typing import List
from passlib.context import CryptContext
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/login/")

Base.metadata.create_all(bind=engine)


# --- Initialization ---

def init_questions(db: Session):
    questions = [
        "بهداشت هم‌اتاقی برای شما چقدر اهمیت دارد؟",
        "نسبت به رفیق بازی (آوردن دوستان به اتاق و ...) هم‌اتاقی چقدر حساسیت دارید؟",
        "نسبت به مصرف دخانیات توسط هم‌اتاقی چقدر حساسیت دارید؟",
        "سر و صدای هم‌اتاقی برای شما چقدر اهمیت دارد؟",
        "اعتقادات هم‌اتاقی برای شما چقدر اهمیت دارد؟",
        "ساعت خواب هم‌اتاقی برای شما چقدر اهمیت دارد؟",
        "اتاق چند نفره ترجیح می‌دی؟"
    ]
    for text in questions:
        if not db.query(QuestionModel).filter(QuestionModel.text == text).first():
            db.add(QuestionModel(text=text))
    db.commit()


def init_admin(db: Session):
    admin_email = "admin@example.com"
    admin_password = pwd_context.hash("adminpassword")
    if not db.query(UserModel).filter(UserModel.email == admin_email).first():
        db_admin = UserModel(
            email=admin_email,
            password=admin_password,
            name="Admin",
            class_name="Admin",
            student_id="admin_001",
            gender="male"
        )
        db.add(db_admin)
        db.commit()
        logger.info(f"Admin user created with email: {admin_email}")


@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    init_questions(db)
    init_admin(db)
    db.close()


# --- Helper Functions ---

def get_user_group(user_id: int, db: Session):
    member = db.query(GroupMemberModel).filter(GroupMemberModel.user_id == user_id).first()
    if not member:
        return None
    return db.query(GroupModel).filter(GroupModel.id == member.group_id).options(
        joinedload(GroupModel.members).joinedload(GroupMemberModel.user)
    ).first()


def calculate_match_percentage(user_answers: List[AnswerModel], potential_answers: List[AnswerModel]):
    criteria = [1, 2, 3, 4, 5, 6]
    max_diff = 4
    total_weighted_diff = 0

    for criterion in criteria:
        user_answer = next((a for a in user_answers if a.question_id == criterion), None)
        potential_answer = next((a for a in potential_answers if a.question_id == criterion), None)
        if user_answer and potential_answer:
            diff = abs(user_answer.value - potential_answer.value)
            total_weighted_diff += (diff / max_diff) * 0.15

    room_size_user = next((a for a in user_answers if a.question_id == 7), None)
    room_size_potential = next((a for a in potential_answers if a.question_id == 7), None)
    room_size_diff = 1 if room_size_user and room_size_potential and room_size_user.value != room_size_potential.value else 0
    total_weighted_diff += room_size_diff * 0.1

    match_score = 1 - total_weighted_diff
    return round(match_score * 100, 2)


# --- Auth Endpoints ---

@app.post("/users/", response_model=User)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    logger.info(f"Creating user with email: {user.email}")
    if db.query(UserModel).filter(UserModel.email == user.email).first():
        raise HTTPException(status_code=400, detail="ایمیل قبلاً ثبت شده است")
    if db.query(UserModel).filter(UserModel.student_id == user.student_id).first():
        raise HTTPException(status_code=400, detail="شماره دانشجویی قبلاً ثبت شده است")

    hashed_password = pwd_context.hash(user.password)
    db_user = UserModel(
        email=user.email,
        password=hashed_password,
        name=user.name,
        class_name=user.class_name,
        student_id=user.student_id,
        gender=user.gender
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"User {db_user.id} created")
    return db_user


@app.post("/login/", response_model=User)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    logger.info(f"Login attempt for email: {login_data.email}")
    user = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not pwd_context.verify(login_data.password, user.password):
        logger.error(f"Login failed for email: {login_data.email}")
        raise HTTPException(status_code=400, detail="ایمیل یا رمز عبور اشتباه است")
    return user


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching user {user_id}")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        logger.error(f"User {user_id} not found")
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return user


# --- Quiz Endpoints ---

@app.get("/questions/", response_model=List[Question])
def get_questions(db: Session = Depends(get_db)):
    logger.info("Fetching all questions")
    questions = db.query(QuestionModel).all()
    if not questions:
        logger.error("No questions found in database")
        raise HTTPException(status_code=404, detail="سوالی یافت نشد")
    return questions


@app.get("/answers/", response_model=List[Answer])
def get_answers(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching answers for user {user_id}")
    answers = db.query(AnswerModel).filter(AnswerModel.user_id == user_id).all()
    if not answers:
        logger.error(f"No answers found for user {user_id}")
        raise HTTPException(status_code=404, detail="پاسخی برای کاربر یافت نشد")
    return answers


@app.put("/answers/{user_id}", response_model=List[Answer])
def update_answers(user_id: int, answers: List[AnswerBase], db: Session = Depends(get_db)):
    logger.info(f"Updating answers for user {user_id}")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")

    db.query(AnswerModel).filter(AnswerModel.user_id == user_id).delete()
    new_answers = []
    for answer in answers:
        db_answer = AnswerModel(
            user_id=user_id,
            question_id=answer.question_id,
            value=answer.value
        )
        db.add(db_answer)
        new_answers.append(db_answer)

    db.commit()
    for answer in new_answers:
        db.refresh(answer)

    logger.info(f"Answers updated for user {user_id}")
    return new_answers


# --- Match Endpoints ---

@app.get("/matches/{user_id}", response_model=List[MatchResponse])
def get_matches(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching matches for user {user_id}")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    user_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user_id).all()
    if len(user_answers) < 7:
        raise HTTPException(status_code=400, detail=f"کاربر تست را کامل نکرده است")

    # لیست کسانی که بهشون درخواست pending ارسال شده یا ازشون دریافت شده
    pending_sent = db.query(RoommateRequestModel).filter(
        RoommateRequestModel.sender_id == user_id,
        RoommateRequestModel.status == "pending"
    ).all()
    pending_received = db.query(RoommateRequestModel).filter(
        RoommateRequestModel.receiver_id == user_id,
        RoommateRequestModel.status == "pending"
    ).all()
    excluded_ids = {r.receiver_id for r in pending_sent} | {r.sender_id for r in pending_received}
    excluded_ids.add(user_id)

    # اعضای گروه خود کاربر
    user_group = get_user_group(user_id, db)
    group_member_ids = set()
    if user_group:
        group_member_ids = {m.user_id for m in user_group.members}
    excluded_ids |= group_member_ids

    potential_users = db.query(UserModel).filter(
        UserModel.id != user_id,
        UserModel.gender == user.gender
    ).all()

    matches = []
    for potential_user in potential_users:
        if potential_user.id in excluded_ids:
            continue
        potential_answers = db.query(AnswerModel).filter(AnswerModel.user_id == potential_user.id).all()
        if len(potential_answers) == 7:
            match_percentage = calculate_match_percentage(user_answers, potential_answers)
            user_data = {
                "id": potential_user.id,
                "email": potential_user.email,
                "name": potential_user.name,
                "class_name": potential_user.class_name,
                "student_id": potential_user.student_id,
                "gender": potential_user.gender,
                "password": None
            }
            matches.append(MatchResponse(user=User(**user_data), match_percentage=match_percentage))

    matches.sort(key=lambda x: x.match_percentage, reverse=True)

    above_50 = [match for match in matches if match.match_percentage > 50]
    below_50 = [match for match in matches if match.match_percentage <= 50]
    result = above_50[:6]
    if len(result) < 6:
        result.extend(below_50[:6 - len(result)])

    logger.info(f"Returning {len(result)} matches for user {user_id}")
    return result


@app.get("/match_percentage/{user1_id}/{user2_id}", response_model=float)
def get_match_percentage(user1_id: int, user2_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching match percentage between user {user1_id} and user {user2_id}")
    user1 = db.query(UserModel).filter(UserModel.id == user1_id).first()
    user2 = db.query(UserModel).filter(UserModel.id == user2_id).first()
    if not user1 or not user2:
        raise HTTPException(status_code=404, detail="یکی از کاربران یافت نشد")

    user1_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user1_id).all()
    user2_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user2_id).all()
    if len(user1_answers) < 7 or len(user2_answers) < 7:
        raise HTTPException(status_code=400, detail="یکی از کاربران تست را کامل نکرده است")

    return calculate_match_percentage(user1_answers, user2_answers)


# --- RoommateRequest Endpoints ---

@app.post("/requests/", response_model=RoommateRequestSchema)
def send_request(request_data: RoommateRequestCreate, db: Session = Depends(get_db)):
    sender_id = request_data.sender_id
    receiver_id = request_data.receiver_id

    logger.info(f"Request from {sender_id} to {receiver_id}")

    if sender_id == receiver_id:
        raise HTTPException(status_code=400, detail="نمی‌توانید به خودتان درخواست بدهید")

    receiver = db.query(UserModel).filter(UserModel.id == receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")

    # بررسی درخواست تکراری (pending)
    existing = db.query(RoommateRequestModel).filter(
        RoommateRequestModel.sender_id == sender_id,
        RoommateRequestModel.receiver_id == receiver_id,
        RoommateRequestModel.status == "pending"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="قبلاً به این کاربر درخواست داده‌اید")

    # بررسی اینکه آیا قبلاً مچ شدن (همان گروه هستن)
    sender_group = get_user_group(sender_id, db)
    if sender_group:
        member_ids = {m.user_id for m in sender_group.members}
        if receiver_id in member_ids:
            raise HTTPException(status_code=400, detail="شما قبلاً با این کاربر مچ شده‌اید")

    db_request = RoommateRequestModel(
        sender_id=sender_id,
        receiver_id=receiver_id,
        status="pending"
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)

    logger.info(f"Request {db_request.id} created")
    return db_request


@app.get("/requests/sent/{user_id}", response_model=List[RoommateRequestSchema])
def get_sent_requests(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching sent requests for user {user_id}")
    requests = db.query(RoommateRequestModel).filter(
        RoommateRequestModel.sender_id == user_id
    ).order_by(RoommateRequestModel.created_at.desc()).all()
    return requests


@app.get("/requests/received/{user_id}", response_model=List[RoommateRequestSchema])
def get_received_requests(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching received requests for user {user_id}")
    requests = db.query(RoommateRequestModel).filter(
        RoommateRequestModel.receiver_id == user_id
    ).order_by(RoommateRequestModel.created_at.desc()).all()
    return requests


@app.put("/requests/{request_id}/accept")
def accept_request(request_id: int, current_user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Accepting request {request_id} by user {current_user_id}")

    req = db.query(RoommateRequestModel).filter(RoommateRequestModel.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")

    if req.receiver_id != current_user_id:
        raise HTTPException(status_code=403, detail="فقط گیرنده درخواست می‌تواند تأیید کند")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="این درخواست قبلاً پردازش شده است")

    sender_id = req.sender_id
    receiver_id = req.receiver_id

    sender_group = get_user_group(sender_id, db)
    receiver_group = get_user_group(receiver_id, db)

    if not sender_group and not receiver_group:
        # حالت ۱: هیچکدوم گروه ندارن → گروه جدید
        logger.info(f"Case 1: Neither has group, creating new group for {sender_id} and {receiver_id}")
        new_group = GroupModel(is_complete=False)
        db.add(new_group)
        db.commit()
        db.refresh(new_group)

        db.add(GroupMemberModel(group_id=new_group.id, user_id=sender_id))
        db.add(GroupMemberModel(group_id=new_group.id, user_id=receiver_id))
        db.commit()

    elif sender_group and not receiver_group:
        # حالت ۲: فرستنده گروه داره، گیرنده نداره
        logger.info(f"Case 2: Sender has group {sender_group.id}, adding receiver {receiver_id}")
        db.add(GroupMemberModel(group_id=sender_group.id, user_id=receiver_id))
        db.commit()

    elif not sender_group and receiver_group:
        # حالت ۳: گیرنده گروه داره، فرستنده نداره
        logger.info(f"Case 3: Receiver has group {receiver_group.id}, adding sender {sender_id}")
        db.add(GroupMemberModel(group_id=receiver_group.id, user_id=sender_id))
        db.commit()

    else:
        # حالت ۴: هر دو گروه دارن → فقط فرستنده می‌ره گروه گیرنده
        logger.info(f"Case 4: Both have groups. Moving sender {sender_id} from group {sender_group.id} to {receiver_group.id}")

        # حذف فرستنده از گروه قدیمی
        old_member = db.query(GroupMemberModel).filter(
            GroupMemberModel.user_id == sender_id,
            GroupMemberModel.group_id == sender_group.id
        ).first()
        if old_member:
            db.delete(old_member)
            db.commit()

        # اضافه به گروه گیرنده
        db.add(GroupMemberModel(group_id=receiver_group.id, user_id=sender_id))
        db.commit()

        # اگه گروه قدیمی خالی شد → حذف
        remaining = db.query(GroupMemberModel).filter(
            GroupMemberModel.group_id == sender_group.id
        ).count()
        if remaining == 0:
            db.query(GroupModel).filter(GroupModel.id == sender_group.id).delete()
            db.commit()

    # رد کردن سایر درخواست‌های pending مرتبط
    # درخواست‌هایی که فرستنده به بقیه داده (دیگه لازم نیست)
    db.query(RoommateRequestModel).filter(
        RoommateRequestModel.sender_id == sender_id,
        RoommateRequestModel.status == "pending"
    ).update({"status": "rejected"})

    # درخواست‌هایی که بقیه به فرستنده داده بودن
    db.query(RoommateRequestModel).filter(
        RoommateRequestModel.receiver_id == sender_id,
        RoommateRequestModel.status == "pending"
    ).update({"status": "rejected"})

    req.status = "accepted"
    db.commit()

    logger.info(f"Request {request_id} accepted successfully")
    return {"message": "درخواست تأیید شد"}


@app.put("/requests/{request_id}/reject")
def reject_request(request_id: int, current_user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Rejecting request {request_id} by user {current_user_id}")

    req = db.query(RoommateRequestModel).filter(RoommateRequestModel.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="درخواست یافت نشد")

    if req.receiver_id != current_user_id:
        raise HTTPException(status_code=403, detail="فقط گیرنده درخواست می‌تواند رد کند")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail="این درخواست قبلاً پردازش شده است")

    req.status = "rejected"
    db.commit()

    logger.info(f"Request {request_id} rejected")
    return {"message": "درخواست رد شد"}


# --- Group Endpoints ---

@app.get("/group/{user_id}")
def get_group(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching group for user {user_id}")
    group = get_user_group(user_id, db)
    if not group:
        return None
    return group


# --- Room Endpoints (public read-only) ---

@app.get("/rooms/", response_model=List[Room])
def get_rooms(db: Session = Depends(get_db)):
    logger.info("Fetching all rooms")
    rooms = db.query(RoomModel).all()
    return rooms


# --- Admin Endpoints ---

@app.post("/admin/login/")
def admin_login(login_data: AdminLoginRequest, db: Session = Depends(get_db)):
    logger.info(f"Admin login attempt for email: {login_data.email}")
    admin = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not admin or not pwd_context.verify(login_data.password, admin.password):
        raise HTTPException(status_code=400, detail="ایمیل یا رمز عبور اشتباه است")
    return {"token": "admin_token"}


def get_admin_token(token: str = Depends(oauth2_scheme)):
    if token != "admin_token":
        raise HTTPException(status_code=403, detail="دسترسی غیرمجاز")
    return token


@app.post("/admin/rooms/", response_model=Room, dependencies=[Depends(get_admin_token)])
def admin_create_room(room: RoomCreate, db: Session = Depends(get_db)):
    logger.info(f"Admin creating room {room.number}")
    existing = db.query(RoomModel).filter(RoomModel.number == room.number).first()
    if existing:
        raise HTTPException(status_code=400, detail="شماره اتاق قبلاً ثبت شده است")
    db_room = RoomModel(
        number=room.number,
        capacity=room.capacity,
        dormitory=room.dormitory,
        current_occupancy=0
    )
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    return db_room


@app.put("/admin/rooms/{room_id}", response_model=Room, dependencies=[Depends(get_admin_token)])
def admin_update_room(room_id: int, room_data: RoomUpdate, db: Session = Depends(get_db)):
    logger.info(f"Admin updating room {room_id}")
    db_room = db.query(RoomModel).filter(RoomModel.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="اتاق یافت نشد")
    if room_data.number is not None:
        db_room.number = room_data.number
    if room_data.capacity is not None:
        db_room.capacity = room_data.capacity
    if room_data.dormitory is not None:
        db_room.dormitory = room_data.dormitory
    if room_data.current_occupancy is not None:
        db_room.current_occupancy = room_data.current_occupancy
    db.commit()
    db.refresh(db_room)
    return db_room


@app.delete("/admin/rooms/{room_id}", dependencies=[Depends(get_admin_token)])
def admin_delete_room(room_id: int, db: Session = Depends(get_db)):
    logger.info(f"Admin deleting room {room_id}")
    db_room = db.query(RoomModel).filter(RoomModel.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="اتاق یافت نشد")
    db.delete(db_room)
    db.commit()
    return {"message": "اتاق حذف شد"}


@app.get("/admin/rooms/", response_model=List[Room], dependencies=[Depends(get_admin_token)])
def admin_rooms(db: Session = Depends(get_db)):
    logger.info("Fetching all rooms for admin")
    rooms = db.query(RoomModel).all()
    return rooms


@app.get("/admin/groups/", response_model=List[GroupSchema], dependencies=[Depends(get_admin_token)])
def admin_groups(db: Session = Depends(get_db)):
    logger.info("Fetching all groups for admin")
    groups = db.query(GroupModel).options(
        joinedload(GroupModel.members).joinedload(GroupMemberModel.user)
    ).all()
    return groups
