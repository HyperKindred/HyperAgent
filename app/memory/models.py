"""Memory data models: SQLAlchemy ORM + Pydantic schemas.

Stores narrative memories with provider-tagged vector embeddings for semantic
(RAG) retrieval. Provider and dimension metadata prevent incompatible vectors
from being compared after a runtime model change.
"""

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.schedule.database import Base
from app.utils.time import utc_now_sql


class Memory(Base):
    """A single narrative memory with semantic embedding."""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, default="general", index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    embedding_fingerprint = Column(String(64), nullable=True, index=True)
    embedding_model = Column(String(160), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    importance = Column(Float, default=0.5)
    source = Column(String(50), default="chat")
    recall_count = Column(Integer, nullable=False, default=0)
    last_recalled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=utc_now_sql())
    updated_at = Column(
        DateTime,
        server_default=utc_now_sql(),
        onupdate=utc_now_sql(),
    )


# ── Pydantic schemas ─────────────────────────────────────────────────


class MemoryCreate(BaseModel):
    """Fields needed to create a new memory."""

    content: str
    category: str = "general"
    importance: float = 0.5
    source: str = "chat"


class MemoryUpdate(BaseModel):
    """User-editable memory fields."""

    content: str | None = Field(default=None, min_length=1, max_length=10000)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    importance: float | None = Field(default=None, ge=0, le=1)


class MemoryResponse(BaseModel):
    """Full memory record returned via API."""

    id: int
    category: str
    content: str
    importance: float
    source: str
    recall_count: int = 0
    last_recalled_at: datetime | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
