from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    email: str
    name: str
    class_name: str
    student_id: str
    gender: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    password: Optional[str] = None

    class Config:
        from_attributes = True


# --- Room ---

class RoomCreate(BaseModel):
    number: str
    capacity: int
    dormitory: str


class RoomUpdate(BaseModel):
    number: Optional[str] = None
    capacity: Optional[int] = None
    dormitory: Optional[str] = None
    current_occupancy: Optional[int] = None


class Room(BaseModel):
    id: int
    number: str
    capacity: int
    dormitory: str
    current_occupancy: int

    class Config:
        from_attributes = True


# --- Group ---

class GroupMemberSchema(BaseModel):
    id: int
    group_id: int
    user: User

    class Config:
        from_attributes = True


class GroupSchema(BaseModel):
    id: int
    is_complete: bool
    members: List[GroupMemberSchema] = []

    class Config:
        from_attributes = True


# --- RoommateRequest ---

class RoommateRequestCreate(BaseModel):
    sender_id: int
    receiver_id: int


class RoommateRequestSchema(BaseModel):
    id: int
    sender: User
    receiver: User
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Quiz ---

class QuestionBase(BaseModel):
    text: str


class Question(QuestionBase):
    id: int

    class Config:
        from_attributes = True


class AnswerBase(BaseModel):
    user_id: int
    question_id: int
    value: int


class Answer(AnswerBase):
    id: int

    class Config:
        from_attributes = True


# --- Auth ---

class LoginRequest(BaseModel):
    email: str
    password: str


class MatchResponse(BaseModel):
    user: User
    match_percentage: float

    class Config:
        from_attributes = True


class AdminLoginRequest(BaseModel):
    email: str
    password: str
