"""Security and operational data. Secret-bearing payloads are encrypted."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from database import Base
from models import utc_now


class Enrollment(Base):
    __tablename__ = "pilot_enrollments"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    class_name = Column(String(100), nullable=False)
    gender = Column(String(20), nullable=False)
    pool = Column(String(100), nullable=False)
    cycle = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="eligible", server_default="eligible")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class AccountSession(Base):
    __tablename__ = "pilot_sessions"
    sid = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    auth_version = Column(Integer, nullable=False)
    refresh_digest = Column(String(64), nullable=False)
    device = Column(String(160), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_used_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class SecurityToken(Base):
    __tablename__ = "pilot_security_tokens"
    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("pilot_enrollments.id"), nullable=True, index=True)
    purpose = Column(String(30), nullable=False)
    approved_email = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class RateBucket(Base):
    __tablename__ = "pilot_rate_buckets"
    key = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class OutboxEvent(Base):
    __tablename__ = "pilot_outbox"
    __table_args__ = (Index("ix_pilot_outbox_due", "status", "next_attempt_at", "lease_until"),)
    id = Column(Integer, primary_key=True)
    event_key = Column(String(200), nullable=False, unique=True)
    purpose = Column(String(40), nullable=False)
    recipient_ref = Column(String(64), nullable=False)
    token_id = Column(Integer, ForeignKey("pilot_security_tokens.id"), nullable=True)
    key_version = Column(String(30), nullable=False)
    encrypted_payload = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(64), nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    failure_code = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class WorkerHeartbeat(Base):
    __tablename__ = "pilot_worker_heartbeats"
    worker_id = Column(String(64), primary_key=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)


class UserBlock(Base):
    __tablename__ = "pilot_blocks"
    __table_args__ = (UniqueConstraint("actor_id", "target_id", name="uq_pilot_block"),)
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportCase(Base):
    __tablename__ = "pilot_support_cases"
    id = Column(Integer, primary_key=True)
    reference = Column(String(40), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String(30), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="open")
    resolution = Column(Text, nullable=True)
    escalated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class DeletionLedger(Base):
    __tablename__ = "pilot_deletion_ledger"
    user_id = Column(Integer, primary_key=True)
    identity_digest = Column(String(64), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
