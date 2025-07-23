from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload
from database import Base, engine, get_db, SessionLocal
from models import User as UserModel, Room as RoomModel, Roommate as RoommateModel, Question as QuestionModel, Answer as AnswerModel, RejectedRoommate as RejectedRoommateModel
from schemas import UserCreate, User, Room, Roommate, RoommateBase, Question, Answer, AnswerBase, LoginRequest, MatchResponse, AdminLoginRequest
from typing import List
from passlib.context import CryptContext
import logging
import traceback

# تنظیم لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# تنظیمات CORS
origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# تنظیمات هش رمز عبور
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# تنظیم OAuth2 برای استخراج توکن
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/login/")

Base.metadata.create_all(bind=engine)

# Initialize questions
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

# Initialize admin user
def init_admin(db: Session):
    admin_email = "admin@example.com"
    admin_password = pwd_context.hash("adminpassword")  # هش کردن رمز عبور ادمین
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
        db_room = RoomModel(owner_id=db_admin.id)
        db.add(db_room)
        db.commit()
        db.refresh(db_room)
        db_roommate = RoommateModel(user_id=db_admin.id, room_id=db_room.id)
        db.add(db_roommate)
        db.commit()
        logger.info(f"Admin user created with email: {admin_email}")

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    init_questions(db)
    init_admin(db)
    db.close()

@app.post("/users/", response_model=User)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    logger.info(f"Creating user with email: {user.email}")
    if db.query(UserModel).filter(UserModel.email == user.email).first():
        raise HTTPException(status_code=400, detail="ایمیل قبلاً ثبت شده است")
    if db.query(UserModel).filter(UserModel.student_id == user.student_id).first():
        raise HTTPException(status_code=400, detail="شماره دانشجویی قبلاً ثبت شده است")
    
    # هش کردن رمز عبور
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
    # Create a room for the user without setting capacity yet
    db_room = RoomModel(owner_id=db_user.id)
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    # Add user to their own room
    db_roommate = RoommateModel(user_id=db_user.id, room_id=db_room.id)
    db.add(db_roommate)
    db.commit()
    logger.info(f"User {db_user.id} created with room {db_room.id}")
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

@app.get("/answers/", response_model=List[Answer])
def get_answers(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching answers for user {user_id}")
    answers = db.query(AnswerModel).filter(AnswerModel.user_id == user_id).all()
    if not answers:
        logger.error(f"No answers found for user {user_id}")
        raise HTTPException(status_code=404, detail="پاسخی برای کاربر یافت نشد")
    return answers

@app.post("/answers/", response_model=List[Answer])
def save_answers(answers: List[AnswerBase], db: Session = Depends(get_db)):
    logger.info(f"Saving answers for user {answers[0].user_id}")
    db_answers = []
    valid_room_sizes = [2, 4, 8, 12]
    for answer in answers:
        if answer.question_id in [1, 2, 3, 4, 5, 6] and answer.value not in range(1, 6):
            logger.error(f"Invalid value {answer.value} for question {answer.question_id}")
            raise HTTPException(status_code=400, detail=f"مقدار پاسخ برای سؤال {answer.question_id} باید بین 1 و 5 باشد")
        if answer.question_id == 7 and answer.value not in valid_room_sizes:
            logger.error(f"Invalid room size {answer.value} for question 7")
            raise HTTPException(status_code=400, detail=f"مقدار پاسخ برای اندازه اتاق باید یکی از {valid_room_sizes} باشد")
        db_answer = AnswerModel(**answer.dict())
        db.add(db_answer)
        db_answers.append(db_answer)
    db.commit()
    for db_answer in db_answers:
        db.refresh(db_answer)
    # Update room capacity based on room_size answer
    room_size_answer = next((a for a in answers if a.question_id == 7), None)
    if room_size_answer:
        user = db.query(UserModel).filter(UserModel.id == room_size_answer.user_id).first()
        room = db.query(RoomModel).filter(RoomModel.owner_id == user.id).first()
        if room:
            room.capacity = room_size_answer.value
            db.commit()
            logger.info(f"Updated room capacity to {room.capacity} for user {user.id}")
    return db_answers

@app.get("/questions/", response_model=List[Question])
def get_questions(db: Session = Depends(get_db)):
    logger.info("Fetching all questions")
    questions = db.query(QuestionModel).all()
    if not questions:
        logger.error("No questions found in database")
        raise HTTPException(status_code=404, detail="سوالی یافت نشد")
    return questions

@app.get("/rooms/{user_id}", response_model=Room)
def get_room(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching room for user {user_id}")
    try:
        room = (
            db.query(RoomModel)
            .outerjoin(RoommateModel, RoomModel.id == RoommateModel.room_id)
            .filter(RoommateModel.user_id == user_id)
            .options(joinedload(RoomModel.roommates).joinedload(RoommateModel.user))
            .first()
        )
        if not room:
            logger.error(f"Room not found for user {user_id}")
            raise HTTPException(status_code=404, detail="اتاق یافت نشد")
        return room
    except Exception as e:
        logger.error(f"Error fetching room for user {user_id}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"خطای سرور: {str(e)}")

@app.post("/roommates/", response_model=Roommate)
def add_roommate(roommate: RoommateBase, db: Session = Depends(get_db)):
    logger.info(f"Adding roommate user_id {roommate.user_id} to room_id {roommate.room_id}")
    room = db.query(RoomModel).filter(RoomModel.id == roommate.room_id).first()
    if not room:
        logger.error(f"Room {roommate.room_id} not found")
        raise HTTPException(status_code=404, detail="اتاق یافت نشد")
    if room.capacity is None:
        logger.error(f"Room {room.id} has no capacity set")
        raise HTTPException(status_code=400, detail="ظرفیت اتاق تنظیم نشده است")
    current_roommates = db.query(RoommateModel).filter(RoommateModel.room_id == room.id).all()
    if len(current_roommates) >= room.capacity:
        logger.error(f"Room {room.id} is full, capacity: {room.capacity}, current: {len(current_roommates)}")
        raise HTTPException(status_code=400, detail="ظرفیت اتاق تکمیل است")
    # Check if user exists
    user = db.query(UserModel).filter(UserModel.id == roommate.user_id).first()
    if not user:
        logger.error(f"User {roommate.user_id} not found")
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    # Check if user is already in another room with others
    existing_roommate = db.query(RoommateModel).filter(RoommateModel.user_id == roommate.user_id).first()
    if existing_roommate:
        current_room = db.query(RoomModel).filter(RoomModel.id == existing_roommate.room_id).first()
        current_roommates_count = db.query(RoommateModel).filter(RoommateModel.room_id == current_room.id).count()
        if current_roommates_count > 1:
            logger.error(f"User {roommate.user_id} is already in a room with {current_roommates_count} roommates")
            raise HTTPException(status_code=400, detail="کاربر مورد نظر در یک اتاق قرار دارد و تمایلی به اضافه شدن به اتاق جدید ندارد")
        # Delete the user's previous room if they are alone
        if current_room and current_roommates_count == 1:
            logger.info(f"Deleting previous room {current_room.id} for user {roommate.user_id}")
            db.delete(existing_roommate)
            db.delete(current_room)
            db.commit()
    # Add user to the new room
    db_roommate = RoommateModel(**roommate.dict())
    db.add(db_roommate)
    db.commit()
    db.refresh(db_roommate)
    logger.info(f"Roommate {db_roommate.id} added to room {room.id}")
    return db_roommate

@app.delete("/roommates/{roommate_id}", response_model=dict)
def remove_roommate(roommate_id: int, db: Session = Depends(get_db)):
    logger.info(f"Removing roommate {roommate_id}")
    db_roommate = db.query(RoommateModel).filter(RoommateModel.id == roommate_id).first()
    if not db_roommate:
        logger.error(f"Roommate {roommate_id} not found")
        raise HTTPException(status_code=404, detail="هم‌اتاقی یافت نشد")
    # Get the room and user
    room = db.query(RoomModel).filter(RoomModel.id == db_roommate.room_id).first()
    user = db.query(UserModel).filter(UserModel.id == db_roommate.user_id).first()
    # Delete the roommate record
    db.delete(db_roommate)
    # Create a new room for the removed user
    new_room = RoomModel(owner_id=user.id)  # Capacity will be set later by quiz
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    # Add the user to their new room
    new_roommate = RoommateModel(user_id=user.id, room_id=new_room.id)
    db.add(new_roommate)
    db.commit()
    logger.info(f"Roommate {roommate_id} removed and moved to new room {new_room.id}")
    return {"message": "هم‌اتاقی حذف شد"}

@app.post("/reject_roommate/")
def reject_roommate(data: RoommateBase, db: Session = Depends(get_db)):
    logger.info(f"Rejecting user {data.user_id} by user {data.room_id}")
    rejected = RejectedRoommateModel(user_id=data.user_id, rejected_by_user_id=data.room_id)
    db.add(rejected)
    db.commit()
    logger.info(f"User {data.user_id} rejected by user {data.room_id}")
    return {"message": "کاربر رد شد"}

@app.get("/matches/{user_id}", response_model=List[MatchResponse])
def get_matches(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching matches for user {user_id}")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        logger.error(f"User {user_id} not found")
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    user_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user_id).all()
    if len(user_answers) < 7:
        logger.error(f"User {user_id} has incomplete quiz, found {len(user_answers)} answers")
        raise HTTPException(status_code=400, detail=f"کاربر تست را کامل نکرده است، فقط {len(user_answers)} پاسخ یافت شد")
    
    matches = []
    rejected_users = db.query(RejectedRoommateModel).filter(RejectedRoommateModel.rejected_by_user_id == user_id).all()
    rejected_user_ids = {r.user_id for r in rejected_users}
    logger.info(f"Found {len(rejected_user_ids)} rejected users for user {user_id}")
    potential_users = db.query(UserModel).filter(UserModel.id != user_id, UserModel.gender == user.gender).all()
    logger.info(f"Found {len(potential_users)} potential users for user {user_id}")
    
    for potential_user in potential_users:
        if potential_user.id in rejected_user_ids:
            logger.debug(f"Skipping rejected user {potential_user.id}")
            continue
        potential_answers = db.query(AnswerModel).filter(AnswerModel.user_id == potential_user.id).all()
        if len(potential_answers) == 7:
            match_percentage = calculate_match_percentage(user_answers, potential_answers)
            if match_percentage > 50:
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
                logger.debug(f"Match found for user {potential_user.id} with percentage {match_percentage}%")
    
    matches.sort(key=lambda x: x.match_percentage, reverse=True)
    logger.info(f"Returning {len(matches)} matches for user {user_id}")
    return matches[:4]

@app.get("/match_percentage/{user1_id}/{user2_id}", response_model=float)
def get_match_percentage(user1_id: int, user2_id: int, db: Session = Depends(get_db)):
    logger.info(f"Calculating match percentage between users {user1_id} and {user2_id}")
    user1_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user1_id).all()
    user2_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user2_id).all()
    if len(user1_answers) < 7 or len(user2_answers) < 7:
        logger.error(f"Insufficient answers: user1 has {len(user1_answers)}, user2 has {len(user2_answers)}")
        raise HTTPException(status_code=400, detail="پاسخ‌های کافی برای محاسبه تطابق وجود ندارد")
    return calculate_match_percentage(user1_answers, user2_answers)

def calculate_match_percentage(user_answers: List[AnswerModel], potential_answers: List[AnswerModel]):
    criteria = [1, 2, 3, 4, 5, 6]  # Question IDs for hygiene, socializing, smoking, noise, beliefs, sleep
    max_diff = 4  # Maximum difference (5 - 1)
    total_weighted_diff = 0

    for criterion in criteria:
        user_answer = next((a for a in user_answers if a.question_id == criterion), None)
        potential_answer = next((a for a in potential_answers if a.question_id == criterion), None)
        if user_answer and potential_answer:
            diff = abs(user_answer.value - potential_answer.value)
            total_weighted_diff += (diff / max_diff) * 0.15  # Each criterion has 0.15 weight

    room_size_user = next((a for a in user_answers if a.question_id == 7), None)
    room_size_potential = next((a for a in potential_answers if a.question_id == 7), None)
    room_size_diff = 1 if room_size_user and room_size_potential and room_size_user.value != room_size_potential.value else 0
    total_weighted_diff += room_size_diff * 0.1  # Room size has 0.1 weight

    match_score = 1 - total_weighted_diff
    return round(match_score * 100, 2)

# مسیرهای ادمین
@app.post("/admin/login/")
def admin_login(login_data: AdminLoginRequest, db: Session = Depends(get_db)):
    logger.info(f"Admin login attempt for email: {login_data.email}")
    admin = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not admin or not pwd_context.verify(login_data.password, admin.password):
        logger.error(f"Admin login failed for email: {login_data.email}")
        raise HTTPException(status_code=400, detail="ایمیل یا رمز عبور اشتباه است")
    return {"token": "admin_token"}

def get_admin_token(token: str = Depends(oauth2_scheme)):
    if token != "admin_token":
        raise HTTPException(status_code=403, detail="دسترسی غیرمجاز")
    return token

@app.get("/admin/rooms/", response_model=List[Room], dependencies=[Depends(get_admin_token)])
def admin_rooms(db: Session = Depends(get_db)):
    logger.info("Fetching all rooms for admin")
    rooms = db.query(RoomModel).options(joinedload(RoomModel.roommates).joinedload(RoommateModel.user)).all()
    if not rooms:
        logger.info("No rooms found")
        return []
    return rooms