from pydantic import BaseModel
from typing import List

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

    class Config:
        orm_mode = True

class RoomBase(BaseModel):
    capacity: int
    owner_id: int

class Room(RoomBase):
    id: int
    roommates: List["Roommate"] = []

    class Config:
        orm_mode = True

class RoommateBase(BaseModel):
    user_id: int
    room_id: int

class Roommate(RoommateBase):
    id: int
    user: User = None

    class Config:
        orm_mode = True

class Question(BaseModel):
    id: int
    text: str

    class Config:
        orm_mode = True

class AnswerBase(BaseModel):
    user_id: int
    question_id: int
    value: int

class Answer(AnswerBase):
    id: int

    class Config:
        orm_mode = True

class LoginRequest(BaseModel):
    email: str
    password: str

class MatchResponse(BaseModel):
    user: User
    match_percentage: float

    class Config:
        orm_mode = True