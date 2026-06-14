"""Data-access layer for personal memories. Dual-session pattern.

- Pass a ``Session`` for test DI or FastAPI dependency injection.
- Auto-create ``Session`` when called standalone (e.g. from tools).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.memory.embeddings import cosine_similarity, get_embedding
from app.memory.models import Memory, MemoryCreate

logger = logging.getLogger(__name__)


class MemoryRepository:
    """CRUD for the ``memories`` table with semantic-search support."""

    def __init__(self, session: Session | None = None):
        self.session = session

    # ── internal helpers ────────────────────────────────────────────

    def _s(self) -> Session:
        if self.session is not None:
            return self.session
        from app.schedule.database import SessionLocal

        return SessionLocal()

    # ── create ──────────────────────────────────────────────────────

    def create_memory(self, data: MemoryCreate) -> Memory:
        """Insert a new memory, automatically generating its embedding."""
        db = self._s()
        entry = Memory(**data.model_dump())
        # Generate embedding via DeepSeek API
        try:
            embedding = get_embedding(data.content)
            entry.embedding = json.dumps(embedding)
        except Exception as exc:
            logger.warning("Embedding API failed for '%s…': %s", data.content[:40], exc)
            entry.embedding = None  # gracefully degrade
        db.add(entry)
        db.commit()
        db.refresh(entry)
        if self.session is None:
            db.close()
        return entry

    # ── semantic search ─────────────────────────────────────────────

    def search_similar(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[Memory]:
        """Embed ``query`` and return the ``top_k`` most semantically similar memories.

        Falls back to text-based LIKE search if the embedding API is
        unavailable.
        """
        all_mems = self._all_with_embeddings(category=category)
        if not all_mems:
            return self._text_fallback(query, category=category)

        try:
            query_emb = get_embedding(query)
        except Exception:
            return self._text_fallback(query, category=category)

        scored: list[tuple[float, Memory]] = []
        for mem in all_mems:
            stored_emb = json.loads(mem.embedding)  # type: ignore[arg-type]
            sim = cosine_similarity(query_emb, stored_emb)
            scored.append((sim, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:top_k]]

    # ── text fallback ───────────────────────────────────────────────

    def search_memories(
        self, query: str, category: str | None = None
    ) -> list[Memory]:
        """Legacy keyword search on ``content``.  Used as fallback."""
        return self._text_fallback(query, category=category)

    def _text_fallback(
        self, query: str, category: str | None = None
    ) -> list[Memory]:
        db = self._s()
        pattern = f"%{query}%"
        q = db.query(Memory).filter(Memory.content.ilike(pattern))
        if category:
            q = q.filter(Memory.category == category)
        results: list[Memory] = q.order_by(Memory.updated_at.desc()).all()
        if self.session is None:
            db.close()
        return results

    # ── list / get ──────────────────────────────────────────────────

    def list_by_category(self, category: str) -> list[Memory]:
        """All memories in a given category."""
        db = self._s()
        results: list[Memory] = (
            db.query(Memory)
            .filter(Memory.category == category)
            .order_by(Memory.created_at.desc())
            .all()
        )
        if self.session is None:
            db.close()
        return results

    def get_all_memories(self) -> list[Memory]:
        """Every stored memory, newest first."""
        db = self._s()
        results: list[Memory] = (
            db.query(Memory).order_by(Memory.created_at.desc()).all()
        )
        if self.session is None:
            db.close()
        return results

    def get_memory(self, memory_id: int) -> Memory | None:
        """Fetch a single memory by id."""
        db = self._s()
        mem: Memory | None = (
            db.query(Memory).filter(Memory.id == memory_id).first()
        )
        if self.session is None:
            db.close()
        return mem

    # ── internals ───────────────────────────────────────────────────

    def _all_with_embeddings(
        self, category: str | None = None
    ) -> list[Memory]:
        """All memories that have a non-null embedding."""
        db = self._s()
        q = db.query(Memory).filter(Memory.embedding.isnot(None))
        if category:
            q = q.filter(Memory.category == category)
        results: list[Memory] = q.all()
        if self.session is None:
            db.close()
        return results

    # ── delete ──────────────────────────────────────────────────────

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by its id. Returns ``True`` if deleted."""
        db = self._s()
        mem: Memory | None = (
            db.query(Memory).filter(Memory.id == memory_id).first()
        )
        if mem is None:
            if self.session is None:
                db.close()
            return False
        db.delete(mem)
        db.commit()
        if self.session is None:
            db.close()
        return True
