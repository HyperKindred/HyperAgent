"""Thread metadata ORM model + Pydantic schemas.

Stored in hyperagent.db (separate from checkpoints.db which stores the actual
conversation state managed by LangGraph/SqliteSaver).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_serializer
from sqlalchemy import Column, DateTime, Integer, String

from app.schedule.database import Base


class Thread(Base):
    """Conversation thread metadata."""
    __tablename__ = "threads"

    id = Column(String(64), primary_key=True)  # "hyperagent-xxxx"
    title = Column(String(200), nullable=False, default="新对话")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    message_count = Column(Integer, default=0)
    model = Column(String(50), default="")


class ThreadCreate(BaseModel):
    thread_id: str
    title: str = "新对话"


class ThreadUpdate(BaseModel):
    title: Optional[str] = None


class ThreadResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    model: str

    model_config = {"from_attributes": True}

    @classmethod
    def _append_z(cls, dt: datetime) -> str:
        """Serialize datetime as ISO 8601 with ``Z`` suffix for UTC.

        The database stores naive UTC datetimes.  Pydantic v2 serializes
        them without timezone info, causing JavaScript ``new Date()`` to
        interpret them as local time (a shift of the timezone offset).
        Appending ``Z`` tells the client they are UTC.
        """
        s = dt.isoformat()
        if dt.tzinfo is None:
            s += "Z"
        return s

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime) -> str:
        return self._append_z(dt)
