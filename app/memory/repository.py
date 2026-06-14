"""Data-access layer for personal memories. Dual-session pattern.

- Pass a ``Session`` for test DI or FastAPI dependency injection.
- Auto-create ``Session`` when called standalone (e.g. from tools).
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.memory.models import Memory, MemoryCreate, MemoryUpdate


class MemoryRepository:
    """CRUD for the ``memories`` table, with upsert-by-key semantics."""

    def __init__(self, session: Session | None = None):
        self.session = session

    # ── internal helpers ────────────────────────────────────────────

    def _s(self) -> Session:
        if self.session is not None:
            return self.session
        from app.schedule.database import SessionLocal

        return SessionLocal()

    # ── create / upsert ─────────────────────────────────────────────

    def create_memory(self, data: MemoryCreate) -> Memory:
        """Upsert by key — if ``key`` exists, update ``value`` and ``category``."""
        db = self._s()
        existing: Memory | None = (
            db.query(Memory).filter(Memory.key == data.key).first()
        )
        if existing:
            existing.value = data.value
            existing.category = data.category
            existing.source = data.source
            db.commit()
            db.refresh(existing)
            result = existing
        else:
            entry = Memory(**data.model_dump())
            db.add(entry)
            db.commit()
            db.refresh(entry)
            result = entry
        if self.session is None:
            db.close()
        return result

    # ── read ────────────────────────────────────────────────────────

    def get_memory_by_key(self, key: str) -> Memory | None:
        """Fetch a single memory by its unique key."""
        db = self._s()
        mem: Memory | None = (
            db.query(Memory).filter(Memory.key == key).first()
        )
        if self.session is None:
            db.close()
        return mem

    def search_memories(
        self, query: str, category: str | None = None
    ) -> list[Memory]:
        """Fuzzy search on both ``key`` and ``value``, optional category filter."""
        db = self._s()
        pattern = f"%{query}%"
        q = db.query(Memory).filter(
            or_(Memory.key.ilike(pattern), Memory.value.ilike(pattern))
        )
        if category:
            q = q.filter(Memory.category == category)
        results: list[Memory] = q.order_by(Memory.updated_at.desc()).all()
        if self.session is None:
            db.close()
        return results

    def list_by_category(self, category: str) -> list[Memory]:
        """All memories in a given category, ordered by key."""
        db = self._s()
        results: list[Memory] = (
            db.query(Memory)
            .filter(Memory.category == category)
            .order_by(Memory.key)
            .all()
        )
        if self.session is None:
            db.close()
        return results

    def get_all_memories(self) -> list[Memory]:
        """Every stored memory, ordered by category then key."""
        db = self._s()
        results: list[Memory] = (
            db.query(Memory).order_by(Memory.category, Memory.key).all()
        )
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

    def delete_memory_by_key(self, key: str) -> bool:
        """Delete a memory by its unique key. Returns ``True`` if deleted."""
        db = self._s()
        mem: Memory | None = (
            db.query(Memory).filter(Memory.key == key).first()
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
