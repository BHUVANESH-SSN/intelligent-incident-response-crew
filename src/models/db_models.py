"""SQLAlchemy ORM models for incident persistence."""

from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class IncidentRecord(Base):
    __tablename__ = "incidents"

    incident_id = Column(String, primary_key=True)
    service = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, nullable=False)
    root_cause = Column(Text)
    root_cause_confidence = Column(Float)
    escalated = Column(Boolean, default=False)
    escalation_reason = Column(Text)
    duration_minutes = Column(Float)
    summary_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
