from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))
    name = Column(String(100))
    class_name = Column(String(100))
    student_id = Column(String(20), unique=True)
    gender = Column(String(20))
    answers = relationship("Answer", back_populates="user")
    group_member = relationship("GroupMember", back_populates="user", uselist=False)
    sent_requests = relationship("RoommateRequest", foreign_keys="RoommateRequest.sender_id", back_populates="sender")
    received_requests = relationship("RoommateRequest", foreign_keys="RoommateRequest.receiver_id", back_populates="receiver")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20), unique=True)
    capacity = Column(Integer)
    dormitory = Column(String(100))
    current_occupancy = Column(Integer, default=0)


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    is_complete = Column(Boolean, default=False)
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_member")


class RoommateRequest(Base):
    __tablename__ = "roommate_requests"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_requests")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_requests")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String(255))
    answers = relationship("Answer", back_populates="question")


class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    value = Column(Integer)
    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")
