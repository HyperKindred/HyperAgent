"""Reminder and notification ORM models + Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.schedule.database import Base


# ── ORM Models ──────────────────────────────────────────────────────────

class Reminder(Base):
    """定时提醒"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    trigger_at = Column(DateTime, nullable=False, index=True)
    recurring = Column(String(100), nullable=True)  # cron expression, e.g. "0 9 * * 1-5"
    status = Column(String(20), nullable=False, default="pending")  # pending | fired | cancelled
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    fired_at = Column(DateTime, nullable=True)


class PendingNotification(Base):
    """待推送通知队列"""
    __tablename__ = "pending_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id"), nullable=True)
    event_type = Column(String(50), nullable=False, default="reminder")  # reminder | suggestion | third_party
    title = Column(String(255), nullable=False)
    body = Column(Text, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    delivered = Column(Boolean, nullable=False, default=False)


# ── Pydantic Schemas ────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    title: str
    description: str = ""
    trigger_at: datetime
    recurring: Optional[str] = None


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    trigger_at: Optional[datetime] = None
    recurring: Optional[str] = None
    status: Optional[str] = None


class ReminderResponse(BaseModel):
    id: int
    title: str
    description: str
    trigger_at: datetime
    recurring: Optional[str] = None
    status: str
    created_at: datetime
    fired_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: int
    event_type: str
    title: str
    body: str
    created_at: datetime
