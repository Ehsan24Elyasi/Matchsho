from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    class_name: str = Field(min_length=1, max_length=100)
    student_id: str = Field(min_length=2, max_length=50)
    gender: Literal["male", "female", "other"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("name", "class_name", "student_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value


class UserCreate(UserBase):
    password: str = Field(min_length=12, max_length=128)


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    class_name: str
    gender: str


class RoommateProfile(PublicUser):
    """Profile fields that are safe to show while deciding on a request."""

    student_id: Optional[str] = None
    answers: Dict[str, int] = Field(default_factory=dict)
    match_percentage: Optional[float] = Field(default=None, ge=0, le=100)


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str = "user"
    is_active: bool = True
    email_verified: bool = False
    created_at: Optional[datetime] = None


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(ge=1, le=100)
    dormitory: str = Field(min_length=1, max_length=100)


class RoomUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: Optional[str] = Field(default=None, min_length=1, max_length=20)
    capacity: Optional[int] = Field(default=None, ge=1, le=100)
    dormitory: Optional[str] = Field(default=None, min_length=1, max_length=100)


class Room(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    capacity: int
    dormitory: str
    current_occupancy: int


class GroupMemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    user: PublicUser


class RoomAssignmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    room: Room


class GroupSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capacity: int
    is_complete: bool
    members: List[GroupMemberSchema] = Field(default_factory=list)
    room_assignment: Optional[RoomAssignmentSchema] = None


class RoommateRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receiver_id: int = Field(gt=0)
    # Kept temporarily for old clients; the server always derives sender_id
    # from the authenticated session and rejects a mismatching value.
    sender_id: Optional[int] = Field(default=None, gt=0)


class RoommateRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: PublicUser
    receiver: PublicUser
    status: str
    created_at: datetime


class Question(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    text: str
    kind: str
    options: List[int] = Field(default_factory=list)
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: int


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # user_id is accepted only for backward compatibility and is never trusted.
    user_id: Optional[int] = None
    question_id: int = Field(gt=0)
    value: int


class Answer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    question_id: int
    value: int


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class AdminLoginRequest(LoginRequest):
    pass


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequest(TokenRequest):
    new_password: str = Field(min_length=12, max_length=128)


class MatchResponse(BaseModel):
    user: PublicUser
    match_percentage: float = Field(ge=0, le=100)


class CsrfResponse(BaseModel):
    csrf_token: str
