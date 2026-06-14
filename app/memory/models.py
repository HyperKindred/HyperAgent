"""Memory data models: SQLAlchemy ORM + Pydantic schemas.

Stores narrative memories with vector embeddings for semantic (RAG) retrieval.
Each memory is a chunk of text the agent deemed worth remembering, stored
alongside a DeepSeek embedding vector that enables similarity search.
"""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from app.schedule.database import Base


class Memory(Base):
    """A single narrative memory with semantic embedding."""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, default="general", index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    importance = Column(Float, default=0.5)
    source = Column(String(50), default="chat")
    created_at = Column(DateTime, server_default=func.datetime("now", "localtime"))
    updated_at = Column(
        DateTime,
        server_default=func.datetime("now", "localtime"),
        onupdate=func.datetime("now", "localtime"),
    )


# ── Pydantic schemas ─────────────────────────────────────────────────


class MemoryCreate(BaseModel):
    """Fields needed to create a new memory."""

    content: str
    category: str = "general"
    importance: float = 0.5
    source: str = "chat"


class MemoryResponse(BaseModel):
    """Full memory record returned via API."""

    id: int
    category: str
    content: str
    importance: float
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
