"""Thread metadata ORM model + Pydantic schemas.

Stored in hyperagent.db (separate from checkpoints.db which stores the actual
conversation state managed by LangGraph/SqliteSaver).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
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
