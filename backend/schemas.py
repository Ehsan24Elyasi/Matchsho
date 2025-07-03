from pydantic import BaseModel
from typing import List, Optional

class UserBase(BaseModel):
    name: str
    email: str
    class_name: str
    student_id: str
    gender: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    class Config:
        from_attributes = True

class RoomBase(BaseModel):
    capacity: int

class RoomCreate(RoomBase):
    owner_id: int

class Room(RoomBase):
    id: int
    owner_id: int
    roommates: List["User"] = []
    class Config:
        from_attributes = True

class RoommateBase(BaseModel):
    user_id: int
    room_id: int

class Roommate(RoommateBase):
    id: int
    user: User
    class Config:
        from_attributes = True

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

class LoginRequest(BaseModel):
    email: str
    password: str

class MatchResponse(BaseModel):
    user: User
    match_percentage: float