from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import Base, engine, get_db, SessionLocal
from models import User as UserModel, Room as RoomModel, Roommate as RoommateModel, Question as QuestionModel, Answer as AnswerModel
from schemas import UserCreate, User, RoomCreate, Room, Roommate, RoommateBase, Question, Answer, AnswerBase, LoginRequest, MatchResponse
from typing import List
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],  # شامل هر دو آدرس
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    init_questions(db)
    db.close()

@app.post("/users/", response_model=User)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserModel).filter(UserModel.email == user.email).first():
        raise HTTPException(status_code=400, detail="ایمیل قبلاً ثبت شده است")
    if db.query(UserModel).filter(UserModel.student_id == user.student_id).first():
        raise HTTPException(status_code=400, detail="شماره دانشجویی قبلاً ثبت شده است")
    db_user = UserModel(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    # Create a room for the user
    db_room = RoomModel(capacity=2, owner_id=db_user.id)  # Default capacity
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    # Add user to their own room
    db_roommate = RoommateModel(user_id=db_user.id, room_id=db_room.id)
    db.add(db_roommate)
    db.commit()
    return db_user

@app.post("/login/", response_model=User)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == login_data.email, UserModel.password == login_data.password).first()
    if not user:
        raise HTTPException(status_code=400, detail="ایمیل یا رمز عبور اشتباه است")
    return user

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return user

@app.post("/answers/", response_model=List[Answer])
def save_answers(answers: List[AnswerBase], db: Session = Depends(get_db)):
    db_answers = []
    for answer in answers:
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
    return db_answers

@app.get("/questions/", response_model=List[Question])
def get_questions(db: Session = Depends(get_db)):
    return db.query(QuestionModel).all()

@app.get("/rooms/{user_id}", response_model=Room)
def get_room(user_id: int, db: Session = Depends(get_db)):
    room = db.query(RoomModel).join(RoommateModel).filter(RoommateModel.user_id == user_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="اتاق یافت نشد")
    room.roommates = db.query(RoommateModel).filter(RoommateModel.room_id == room.id).all()
    return room

@app.post("/roommates/", response_model=Roommate)
def add_roommate(roommate: RoommateBase, db: Session = Depends(get_db)):
    room = db.query(RoomModel).filter(RoomModel.id == roommate.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="اتاق یافت نشد")
    if db.query(RoommateModel).filter(RoommateModel.room_id == room.id).count() >= room.capacity:
        raise HTTPException(status_code=400, detail="ظرفیت اتاق تکمیل است")
    db_roommate = RoommateModel(**roommate.dict())
    db.add(db_roommate)
    db.commit()
    db.refresh(db_roommate)
    return db_roommate

@app.delete("/roommates/{roommate_id}")
def remove_roommate(roommate_id: int, db: Session = Depends(get_db)):
    db_roommate = db.query(RoommateModel).filter(RoommateModel.id == roommate_id).first()
    if not db_roommate:
        raise HTTPException(status_code=404, detail="هم‌اتاقی یافت نشد")
    db.delete(db_roommate)
    db.commit()
    return {"message": "هم‌اتاقی حذف شد"}

@app.get("/matches/{user_id}", response_model=List[MatchResponse])
def get_matches(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    user_answers = db.query(AnswerModel).filter(AnswerModel.user_id == user_id).all()
    if not user_answers:
        raise HTTPException(status_code=400, detail="کاربر تست را کامل نکرده است")
    
    matches = []
    potential_users = db.query(UserModel).filter(UserModel.id != user_id, UserModel.gender == user.gender).all()
    for potential_user in potential_users:
        potential_answers = db.query(AnswerModel).filter(AnswerModel.user_id == potential_user.id).all()
        if potential_answers:
            match_percentage = calculate_match_percentage(user_answers, potential_answers)
            if match_percentage > 50:
                matches.append(MatchResponse(user=potential_user, match_percentage=match_percentage))
    
    matches.sort(key=lambda x: x.match_percentage, reverse=True)
    return matches[:4]

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