from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    name = Column(String)
    class_name = Column(String)
    student_id = Column(String, unique=True)
    gender = Column(String)
    rooms = relationship("Room", back_populates="owner")
    roommates = relationship("Roommate", back_populates="user")
    answers = relationship("Answer", back_populates="user")
    rejected_roommates = relationship("RejectedRoommate", back_populates="user", foreign_keys="RejectedRoommate.user_id")
    rejected_by = relationship("RejectedRoommate", back_populates="rejected_by_user", foreign_keys="RejectedRoommate.rejected_by_user_id")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    capacity = Column(Integer, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="rooms")
    roommates = relationship("Roommate", back_populates="room", cascade="all, delete-orphan")

class Roommate(Base):
    __tablename__ = "roommates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    user = relationship("User", back_populates="roommates")
    room = relationship("Room", back_populates="roommates")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String)
    answers = relationship("Answer", back_populates="question")

class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    value = Column(Integer)
    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")

class RejectedRoommate(Base):
    __tablename__ = "rejected_roommates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    rejected_by_user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="rejected_roommates", foreign_keys=[user_id])
    rejected_by_user = relationship("User", back_populates="rejected_by", foreign_keys=[rejected_by_user_id])