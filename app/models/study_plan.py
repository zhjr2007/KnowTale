from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    plan_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("User", backref="study_plans")
    course = relationship("Course", backref="study_plans")


class StudyPlanItem(Base):
    __tablename__ = "study_plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("study_plans.id"), nullable=False, index=True)
    day = Column(Integer, nullable=False)
    knowledge_point = Column(String(200), nullable=False)
    task_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    is_completed = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)

    plan = relationship("StudyPlan", backref="items")
