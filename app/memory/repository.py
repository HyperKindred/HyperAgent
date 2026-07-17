"""Data-access layer for personal memories. Dual-session pattern.

- Pass a ``Session`` for test DI or FastAPI dependency injection.
- Auto-create ``Session`` when called standalone (e.g. from tools).
"""

from __future__ import annotations

import json
import logging
import math
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.memory.embeddings import cosine_similarity, get_embedding_result
from app.memory.models import Memory, MemoryCreate, MemoryUpdate
from app.memory.store import MemoryWriteResult
from app.utils.time import ensure_utc, now as utc_now

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CANDIDATES = 100
_DUPLICATE_SIMILARITY_THRESHOLD = 0.90


def _context_score(memory: Memory, as_of: datetime) -> float:
    """Rank prompt memories without mutating user-defined importance.

    Importance remains the dominant signal. Recency and genuine recall add a
    bounded adjustment so stale, low-priority memories gradually make room
    for relevant current context.
    """
    importance = min(1.0, max(0.0, float(memory.importance or 0.0)))
    reference = (
        ensure_utc(memory.last_recalled_at)
        or ensure_utc(memory.updated_at)
        or ensure_utc(memory.created_at)
    )
    age_days = max(0.0, (as_of - reference).total_seconds() / 86_400) if reference else 0.0
    freshness = math.exp(-age_days / 365.0)
    recall_strength = min(1.0, math.log1p(memory.recall_count or 0) / math.log(11))
    stability = 0.65 + 0.20 * freshness + 0.15 * recall_strength
    return importance * stability + 0.05 * recall_strength


def _invalidate_prompt_memory_cache() -> None:
    """Avoid a module cycle while keeping prompt memory fresh after writes."""
    from app.memory.context import invalidate_memory_context

    invalidate_memory_context()


class MemoryRepository:
    """CRUD for the ``memories`` table with semantic-search support."""

    def __init__(self, session: Session | None = None):
        self.session = session

    # ── session helper ─────────────────────────────────────────────

    @contextmanager
    def _session(self):
        """Provide a transactional scope.  When a session was injected (e.g.
        by a test fixture) yield it directly; otherwise create, commit on
        success, rollback on error, and always close."""
        if self.session is not None:
            yield self.session
        else:
            from app.schedule.database import SessionLocal

            db = SessionLocal()
            try:
                yield db
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    # ── create ──────────────────────────────────────────────────────

    def create_memory(self, data: MemoryCreate) -> Memory:
        """Insert a new memory, automatically generating its embedding."""
        with self._session() as db:
            entry = Memory(**data.model_dump())
            # Embedding failures never prevent the narrative memory from saving.
            try:
                result = get_embedding_result(data.content)
                if result:
                    entry.embedding = json.dumps(result.vector)
                    entry.embedding_fingerprint = result.fingerprint
                    entry.embedding_model = result.model
                    entry.embedding_dimensions = result.dimensions
            except Exception as exc:
                logger.warning("Embedding API failed while saving memory: %s", exc)
                entry.embedding = None  # gracefully degrade
            db.add(entry)
            db.commit()
            db.refresh(entry)
            _invalidate_prompt_memory_cache()
            return entry

    def remember_memory(self, data: MemoryCreate) -> MemoryWriteResult:
        """Create a memory or consolidate an extremely similar existing fact.

        This path is intended for agent-driven remembering. Manual CRUD and
        imports retain their explicit duplicate semantics.
        """
        try:
            embedding_result = get_embedding_result(data.content)
        except Exception as exc:
            logger.warning("Embedding API failed while checking duplicate memory: %s", exc)
            embedding_result = None

        with self._session() as db:
            exact = db.query(Memory).filter(Memory.content == data.content).first()
            duplicate = exact
            if duplicate is None and embedding_result is not None:
                candidates = (
                    db.query(Memory)
                    .filter(Memory.embedding.isnot(None))
                    .filter(Memory.embedding_fingerprint == embedding_result.fingerprint)
                    .filter(Memory.embedding_dimensions == embedding_result.dimensions)
                    .order_by(Memory.updated_at.desc())
                    .limit(self._MAX_SEARCH_CANDIDATES)
                    .all()
                )
                best_score = -1.0
                for candidate in candidates:
                    try:
                        stored = json.loads(candidate.embedding)
                        score = cosine_similarity(embedding_result.vector, stored)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if score > best_score:
                        duplicate = candidate
                        best_score = score
                if best_score < _DUPLICATE_SIMILARITY_THRESHOLD:
                    duplicate = None

            if duplicate is not None:
                duplicate.importance = max(duplicate.importance or 0.0, data.importance)
                if duplicate.category == "general" and data.category != "general":
                    duplicate.category = data.category
                db.commit()
                db.refresh(duplicate)
                _invalidate_prompt_memory_cache()
                return MemoryWriteResult(entry=duplicate, created=False)

            entry = Memory(**data.model_dump())
            if embedding_result is not None:
                entry.embedding = json.dumps(embedding_result.vector)
                entry.embedding_fingerprint = embedding_result.fingerprint
                entry.embedding_model = embedding_result.model
                entry.embedding_dimensions = embedding_result.dimensions
            db.add(entry)
            db.commit()
            db.refresh(entry)
            _invalidate_prompt_memory_cache()
            return MemoryWriteResult(entry=entry, created=True)

    # ── semantic search ─────────────────────────────────────────────

    def search_similar(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[Memory]:
        """Embed ``query`` and return the ``top_k`` most semantically similar memories.

        Falls back to text-based LIKE search if the embedding API is
        unavailable.

        Note: currently performs brute-force cosine similarity over up to
        ``_MAX_SEARCH_CANDIDATES`` memories that have embeddings.  A dedicated
        vector index (e.g. sqlite-vec) would eliminate the full scan.
        """
        try:
            result = get_embedding_result(query)
        except Exception:
            return self._text_fallback(query, category=category)
        if result is None:
            return self._text_fallback(query, category=category)

        all_mems = self._all_with_embeddings(
            category=category,
            fingerprint=result.fingerprint,
            dimensions=result.dimensions,
        )
        if not all_mems:
            return self._text_fallback(query, category=category)

        scored: list[tuple[float, Memory]] = []
        for mem in all_mems:
            stored_emb = json.loads(mem.embedding)  # type: ignore[arg-type]
            if len(stored_emb) != result.dimensions:
                continue
            sim = cosine_similarity(result.vector, stored_emb)
            scored.append((sim, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:top_k]]

    # ── text fallback ───────────────────────────────────────────────

    _MAX_TEXT_FALLBACK = 20

    def search_memories(
        self, query: str, category: str | None = None
    ) -> list[Memory]:
        """Legacy keyword search on ``content``.  Used as fallback."""
        return self._text_fallback(query, category=category)

    def _text_fallback(
        self, query: str, category: str | None = None
    ) -> list[Memory]:
        with self._session() as db:
            pattern = f"%{query}%"
            q = db.query(Memory).filter(Memory.content.ilike(pattern))
            if category:
                q = q.filter(Memory.category == category)
            return (
                q.order_by(Memory.updated_at.desc())
                .limit(self._MAX_TEXT_FALLBACK)
                .all()
            )

    # ── list / get ──────────────────────────────────────────────────

    def list_by_category(self, category: str) -> list[Memory]:
        """All memories in a given category."""
        with self._session() as db:
            return (
                db.query(Memory)
                .filter(Memory.category == category)
                .order_by(Memory.created_at.desc())
                .all()
            )

    def get_all_memories(self) -> list[Memory]:
        """Every stored memory, newest first."""
        with self._session() as db:
            return db.query(Memory).order_by(Memory.created_at.desc()).all()

    def get_top_memories(self, limit: int = 5) -> list[Memory]:
        """Most relevant memories for system-prompt injection.

        The ranking preserves user importance while applying bounded recency
        and recall adjustments. Only a capped candidate set is loaded.
        """
        with self._session() as db:
            candidates = (
                db.query(Memory)
                .order_by(Memory.importance.desc(), Memory.updated_at.desc())
                .limit(_MAX_CONTEXT_CANDIDATES)
                .all()
            )
            as_of = utc_now()
            candidates.sort(
                key=lambda entry: (
                    _context_score(entry, as_of),
                    entry.updated_at or entry.created_at or datetime.min,
                ),
                reverse=True,
            )
            return candidates[:limit]

    def get_memory(self, memory_id: int) -> Memory | None:
        """Fetch a single memory by id."""
        with self._session() as db:
            return db.query(Memory).filter(Memory.id == memory_id).first()

    def mark_recalled(self, memory_ids: list[int]) -> None:
        """Record that the returned memories were actually shown to the agent."""
        ids = list(dict.fromkeys(memory_ids))
        if not ids:
            return
        with self._session() as db:
            recalled_at = utc_now()
            entries = db.query(Memory).filter(Memory.id.in_(ids)).all()
            for entry in entries:
                entry.recall_count = (entry.recall_count or 0) + 1
                entry.last_recalled_at = recalled_at
            db.commit()

    def update_memory(self, memory_id: int, data: MemoryUpdate) -> Memory | None:
        """Update a memory and regenerate its vector if its text changed."""
        with self._session() as db:
            entry = db.query(Memory).filter(Memory.id == memory_id).first()
            if entry is None:
                return None

            values = data.model_dump(exclude_none=True)
            content_changed = "content" in values and values["content"] != entry.content
            for name, value in values.items():
                setattr(entry, name, value)

            if content_changed:
                entry.embedding = None
                entry.embedding_fingerprint = None
                entry.embedding_model = None
                entry.embedding_dimensions = None
                try:
                    result = get_embedding_result(entry.content)
                    if result:
                        entry.embedding = json.dumps(result.vector)
                        entry.embedding_fingerprint = result.fingerprint
                        entry.embedding_model = result.model
                        entry.embedding_dimensions = result.dimensions
                except Exception as exc:
                    logger.warning("Embedding API failed while updating memory %d: %s", memory_id, exc)

            db.commit()
            db.refresh(entry)
            _invalidate_prompt_memory_cache()
            return entry

    def content_exists(self, content: str) -> bool:
        """Return whether an exact narrative memory is already stored."""
        with self._session() as db:
            return db.query(Memory.id).filter(Memory.content == content).first() is not None

    # ── internals ───────────────────────────────────────────────────

    # Max candidates for brute-force cosine similarity scan.
    # A dedicated vector index (Phase 3.1) will eliminate this limit.
    _MAX_SEARCH_CANDIDATES = 200

    def _all_with_embeddings(
        self,
        category: str | None = None,
        fingerprint: str | None = None,
        dimensions: int | None = None,
    ) -> list[Memory]:
        """Up to ``_MAX_SEARCH_CANDIDATES`` memories that have a non-null embedding.

        Biases toward recent memories (most likely to be relevant).
        """
        with self._session() as db:
            q = db.query(Memory).filter(Memory.embedding.isnot(None))
            if fingerprint:
                q = q.filter(Memory.embedding_fingerprint == fingerprint)
            if dimensions is not None:
                q = q.filter(Memory.embedding_dimensions == dimensions)
            if category:
                q = q.filter(Memory.category == category)
            return (
                q.order_by(Memory.updated_at.desc())
                .limit(self._MAX_SEARCH_CANDIDATES)
                .all()
            )

    # ── delete ──────────────────────────────────────────────────────

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by its id. Returns ``True`` if deleted."""
        with self._session() as db:
            mem = db.query(Memory).filter(Memory.id == memory_id).first()
            if mem is None:
                return False
            db.delete(mem)
            db.commit()
            _invalidate_prompt_memory_cache()
            return True
