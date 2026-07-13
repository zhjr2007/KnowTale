from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String(200), nullable=False)
    question_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    course = relationship("Course", backref="quizzes")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    content = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False)
    options = Column(Text, nullable=True)
    correct_answer = Column(Text, nullable=False)
    knowledge_point = Column(String(200), nullable=True)
    difficulty = Column(String(20), default="medium")
    quiz = relationship("Quiz", backref="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    score = Column(Integer, default=0)
    total = Column(Integer, default=0)
    completed_at = Column(DateTime, default=datetime.utcnow)
    quiz = relationship("Quiz", backref="attempts")
    student = relationship("User", backref="quiz_attempts")


class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    attempt_id = Column(Integer, ForeignKey("quiz_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    student_answer = Column(Text, nullable=False)
    is_correct = Column(Integer, default=0)
    feedback = Column(Text, nullable=True)
    attempt = relationship("QuizAttempt", backref="answers")


class WrongBookRecord(Base):
    __tablename__ = "wrong_book_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    question_content = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    student_answer = Column(Text, nullable=False)
    knowledge_point = Column(String(200), nullable=True)
    question_type = Column(String(20), default="choice")
    source_quiz_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    review_count = Column(Integer, default=0)
    next_review_date = Column(Date, nullable=True)
    last_review_at = Column(DateTime, nullable=True)
    student = relationship("User", backref="wrong_records")
    course = relationship("Course", backref="wrong_records")
