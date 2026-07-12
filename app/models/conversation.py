from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    speaker_type = Column(String(20), nullable=False)
    speaker_id = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    knowledge_tag = Column(String(200), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", backref="conversations")

    def __repr__(self):
        return f"<Conversation course={self.course_id} speaker={self.speaker_type}:{self.speaker_id}>"


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)
    report_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", backref="weekly_reports")

    def __repr__(self):
        return f"<WeeklyReport course={self.course_id} week={self.week_start}~{self.week_end}>"
