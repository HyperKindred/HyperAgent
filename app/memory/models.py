"""Memory data models: SQLAlchemy ORM + Pydantic schemas.

Stores personal facts about the user that the agent remembers across sessions.
Uses a key-value design with categories for organization.
"""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.schedule.database import Base


class Memory(Base):
    """A single stored fact about the user."""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, default="general", index=True)
    key = Column(String(200), nullable=False, index=True, unique=True)
    value = Column(Text, nullable=False)
    source = Column(String(50), default="chat")
    created_at = Column(DateTime, server_default=func.datetime("now", "localtime"))
    updated_at = Column(
        DateTime,
        server_default=func.datetime("now", "localtime"),
        onupdate=func.datetime("now", "localtime"),
    )


# ── Pydantic schemas ─────────────────────────────────────────────────


class MemoryCreate(BaseModel):
    """Fields needed to create or update a memory."""

    category: str = "general"
    key: str
    value: str
    source: str = "chat"


class MemoryUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""

    category: str | None = None
    value: str | None = None


class MemoryResponse(BaseModel):
    """Full memory record returned via API."""

    id: int
    category: str
    key: str
    value: str
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
