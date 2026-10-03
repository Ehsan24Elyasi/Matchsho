"""Pilot domain persistence. Legacy tables remain available for reviewed migration."""
from sqlalchemy import (
    JSON,
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

from database import Base
from models import utc_now


class Questionnaire(Base):
    __tablename__ = "pilot_questionnaires"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    version = Column(Integer, nullable=False, default=2)
    revision = Column(Integer, nullable=False, default=0)
    answers = Column(JSON, nullable=False, default=dict)
    capacities = Column(JSON, nullable=False, default=list)
    complete = Column(Boolean, nullable=False, default=False)
    draft = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Invitation(Base):
    __tablename__ = "pilot_invitations"
    __table_args__ = (UniqueConstraint("active_key", name="uq_pilot_invitation_active"),
                      CheckConstraint("status IN ('pending','needs_reconfirmation','accepted','rejected','cancelled','expired')", name="ck_pilot_invitation_status"),
                      CheckConstraint("capacity >= 2", name="ck_pilot_invitation_capacity"),
                      Index("ix_pilot_invitation_status_expiry", "status", "expires_at"))
    id = Column(Integer, primary_key=True)
    initiator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    capacity = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    active_key = Column(String(150), nullable=True)
    snapshot = Column(JSON, nullable=False, default=dict)
    approvals = Column(JSON, nullable=False, default=list)
    reason = Column(String(100), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Departure(Base):
    __tablename__ = "pilot_departures"
    __table_args__ = (UniqueConstraint("active_key", name="uq_pilot_departure_active"),
                     CheckConstraint("status IN ('pending','approved','rejected')", name="ck_pilot_departure_status"))
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    active_key = Column(String(60), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    reason = Column(Text, nullable=False)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class DomainAudit(Base):
    __tablename__ = "pilot_domain_audit"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(40), nullable=False)
    target_id = Column(Integer, nullable=True)
    reason = Column(Text, nullable=False, default="")
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class Notification(Base):
    __tablename__ = "pilot_notifications"
    __table_args__ = (UniqueConstraint("event_key", "user_id", name="uq_pilot_notification_event"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key = Column(String(160), nullable=False)
    kind = Column(String(50), nullable=False)
    message = Column(String(500), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(Integer, nullable=True)
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class InvitationParticipant(Base):
    __tablename__ = "pilot_invitation_participants"
    invitation_id = Column(Integer, ForeignKey("pilot_invitations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)


class CommandReceipt(Base):
    __tablename__ = "pilot_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "action", "key", name="uq_pilot_command_receipt"),)
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(100), nullable=False)
    key = Column(String(100), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class AllocationHistory(Base):
    __tablename__ = "pilot_allocation_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id = Column(Integer, nullable=False)
    room_id = Column(Integer, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
