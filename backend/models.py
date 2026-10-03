from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("gender IN ('male', 'female', 'other')", name="ck_users_gender"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("student_id", name="uq_users_student_id"),
    )

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    class_name = Column(String(100), nullable=False)
    student_id = Column(String(50), nullable=False)
    gender = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False, default="user", server_default="user")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    email_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    auth_version = Column(Integer, nullable=False, default=1, server_default="1")
    account_status = Column(String(30), nullable=False, default="active", server_default="active")
    discovery_consent = Column(Boolean, nullable=False, default=False, server_default="false")
    explanation_consent = Column(Boolean, nullable=False, default=False, server_default="false")
    consent_version = Column(Integer, nullable=False, default=1, server_default="1")
    notification_email = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    answers = relationship("Answer", back_populates="user", cascade="all, delete-orphan")
    group_member = relationship("GroupMember", back_populates="user", uselist=False)
    sent_requests = relationship(
        "RoommateRequest",
        foreign_keys="RoommateRequest.sender_id",
        back_populates="sender",
        cascade="all, delete-orphan",
    )
    received_requests = relationship(
        "RoommateRequest",
        foreign_keys="RoommateRequest.receiver_id",
        back_populates="receiver",
        cascade="all, delete-orphan",
    )
    refresh_sessions = relationship("RefreshSession", back_populates="user", cascade="all, delete-orphan")
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (UniqueConstraint("jti", name="uq_refresh_sessions_jti"),)

    id = Column(Integer, primary_key=True)
    jti = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    user = relationship("User", back_populates="refresh_sessions")


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
        CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_auth_tokens_purpose"),
    )

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = Column(String(30), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    user = relationship("User", back_populates="auth_tokens")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("key", name="uq_questions_key"),)

    id = Column(Integer, primary_key=True)
    key = Column(String(60), nullable=False)
    text = Column(String(500), nullable=False)
    kind = Column(String(20), nullable=False, default="scale")
    min_value = Column(Integer, nullable=True)
    max_value = Column(Integer, nullable=True)
    options_json = Column(Text, nullable=True)
    weight = Column(Integer, nullable=False, default=15)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_answers_user_question"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    value = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("dormitory", "number", name="uq_rooms_dormitory_number"),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
        CheckConstraint("current_occupancy >= 0", name="ck_rooms_occupancy_nonnegative"),
        CheckConstraint("current_occupancy <= capacity", name="ck_rooms_occupancy_within_capacity"),
    )

    id = Column(Integer, primary_key=True)
    number = Column(String(20), nullable=False)
    capacity = Column(Integer, nullable=False)
    dormitory = Column(String(100), nullable=False)
    pool = Column(String(100), nullable=True)
    cycle = Column(String(100), nullable=True)
    reconciliation_required = Column(Boolean, nullable=False, default=False, server_default="true")
    current_occupancy = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    assignments = relationship("RoomAssignment", back_populates="room", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (CheckConstraint("capacity > 0", name="ck_groups_capacity_positive"),)

    id = Column(Integer, primary_key=True)
    capacity = Column(Integer, nullable=False, default=2, server_default="2")
    is_complete = Column(Boolean, nullable=False, default=False, server_default="false")
    membership_revision = Column(Integer, nullable=False, default=1, server_default="1")
    pool = Column(String(100), nullable=True)
    cycle = Column(String(100), nullable=True)
    reconciliation_required = Column(Boolean, nullable=False, default=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    room_assignment = relationship("RoomAssignment", back_populates="group", uselist=False)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
        UniqueConstraint("user_id", name="uq_group_members_user_id"),
    )

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_member")


class RoomAssignment(Base):
    __tablename__ = "room_assignments"
    __table_args__ = (UniqueConstraint("group_id", name="uq_room_assignments_group_id"),)

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    room = relationship("Room", back_populates="assignments")
    group = relationship("Group", back_populates="room_assignment")


class RoommateRequest(Base):
    __tablename__ = "roommate_requests"
    __table_args__ = (
        Index("ix_requests_sender_status", "sender_id", "status"),
        Index("ix_requests_receiver_status", "receiver_id", "status"),
        UniqueConstraint("active_pair_key", name="uq_requests_active_pair"),
        CheckConstraint("sender_id <> receiver_id", name="ck_requests_distinct_users"),
        CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'cancelled')", name="ck_request_status"),
    )

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    # Set only while a request is pending.  A canonical pair key makes the
    # database reject both duplicate directions under concurrent requests.
    active_pair_key = Column(String(50), nullable=True)
    reason = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_requests")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_requests")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(50), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
