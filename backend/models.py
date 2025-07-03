from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    class_name = Column(String, nullable=False)
    student_id = Column(String, unique=True, nullable=False)
    gender = Column(String, nullable=False)
    rooms = relationship("Room", back_populates="owner")
    answers = relationship("Answer", back_populates="user")
    roommates = relationship("Roommate", back_populates="user")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    capacity = Column(Integer, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="rooms")
    roommates = relationship("Roommate", back_populates="room")

class Roommate(Base):
    __tablename__ = "roommates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    user = relationship("User", back_populates="roommates")
    room = relationship("Room", back_populates="roommates")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    answers = relationship("Answer", back_populates="question")

class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    value = Column(Integer, nullable=False)
    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")