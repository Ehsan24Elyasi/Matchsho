from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ClaimRequest(StrictModel):
    student_id: str = Field(min_length=1, max_length=50)
    email: EmailStr | None = None


class PasswordToken(StrictModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class TokenInput(StrictModel):
    token: str = Field(min_length=20, max_length=200)


class EmailInput(StrictModel):
    email: EmailStr


class RosterRow(StrictModel):
    student_id: str = Field(min_length=1, max_length=50)
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    class_name: str = Field(min_length=1, max_length=100)
    gender: Literal["male", "female", "other"]
    pool: str = Field(min_length=1, max_length=100)
    cycle: str = Field(min_length=1, max_length=100)

    @field_validator("student_id", "name", "class_name", "pool", "cycle")
    @classmethod
    def no_blank(cls, value):
        if not value.strip():
            raise ValueError("مقدار خالی مجاز نیست")
        return value.strip()


class RosterImport(StrictModel):
    rows: list[RosterRow] = Field(min_length=1, max_length=1000)
    dry_run: bool = True
    reason: str = Field(min_length=5, max_length=1000)
    allow_legacy_email_rebind: bool = False


class ProfilePatch(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    class_name: str = Field(min_length=1, max_length=100)


class ConsentPatch(StrictModel):
    discovery: bool
    explanations: bool


class NotificationPreference(StrictModel):
    email: bool


class ReportInput(StrictModel):
    target_id: int | None = Field(default=None, gt=0)
    category: Literal["harassment", "identity", "technical", "other"]
    description: str = Field(default="", max_length=2000)


class CorrectionInput(StrictModel):
    field: Literal["email", "student_id", "pool", "cycle", "other"]
    description: str = Field(min_length=5, max_length=2000)


class ClosureInput(StrictModel):
    delete: bool = True
    reason: str = Field(default="", max_length=500)


class CaseResolution(StrictModel):
    status: Literal["reviewing", "resolved", "dismissed"]
    reason: str = Field(min_length=5, max_length=2000)


class EnrollmentCorrection(StrictModel):
    field: Literal["email", "student_id", "pool", "cycle", "status"]
    value: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=5, max_length=1000)
    dry_run: bool = True


class SecurityAction(StrictModel):
    action: Literal["suspend", "reactivate", "revoke_sessions"]
    reason: str = Field(min_length=5, max_length=1000)


class DeliveryRetry(StrictModel):
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value
