from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), index=True, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invite_code = Column(String(6), unique=True, index=True, nullable=True)

    knowledge_base_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="active")

    teacher_role_card = Column(Text, nullable=True)
    student_roles_config = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("User", backref="courses")

    def __repr__(self):
        return f"<Course {self.name}>"


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", backref="enrollments")
    student = relationship("User", backref="enrollments")

    def __repr__(self):
        return f"<Enrollment course={self.course_id} student={self.student_id}>"
