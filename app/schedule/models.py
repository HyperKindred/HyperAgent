from datetime import datetime

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import Column, DateTime, Integer, String, Text

from app.schedule.database import Base
from app.config import settings
from app.utils.time import to_local, utc_now_sql


# ── SQLAlchemy ORM Model ──────────────────────────────────────────────

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="pending")  # pending | completed | cancelled
    priority = Column(String(20), default="normal")  # low | normal | high
    category = Column(String(50), default="")
    created_at = Column(DateTime, server_default=utc_now_sql())
    updated_at = Column(
        DateTime,
        server_default=utc_now_sql(),
        onupdate=utc_now_sql(),
    )


# ── Pydantic Schemas ──────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str
    description: str = ""
    start_time: datetime
    end_time: datetime | None = None
    status: str = "pending"
    priority: str = "normal"
    category: str = ""


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None


class EventResponse(BaseModel):
    id: int
    title: str
    description: str
    start_time: datetime
    end_time: datetime | None
    status: str
    priority: str
    category: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_serializer("start_time", "end_time", when_used="unless-none")
    def serialize_local_datetime(self, dt: datetime) -> str:
        """Calendar UI receives wall-clock values in the configured timezone."""
        return to_local(dt, settings.timezone).replace(tzinfo=None).isoformat()
