from pydantic import BaseModel
from typing import Optional, List

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

class RoomBase(BaseModel):
    capacity: Optional[int] = None
    owner_id: int

class Room(RoomBase):
    id: int
    roommates: List['Roommate'] = []

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

    class Config:
        from_attributes = True

class AdminLoginRequest(BaseModel):
    email: str
    password: str