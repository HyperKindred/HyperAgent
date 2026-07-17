"""Stable memory-store contract for application-facing memory operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.memory.models import Memory, MemoryCreate, MemoryUpdate


@dataclass(frozen=True)
class MemoryWriteResult:
    entry: Memory
    created: bool


@runtime_checkable
class MemoryStore(Protocol):
    """Contract used by the agent, REST API and prompt-context builder.

    Implementations own their storage and vector mechanics.  Callers operate
    on narrative records only, allowing a future SQLite vector extension or a
    local vector store to replace the current SQLAlchemy implementation.
    """

    def create_memory(self, data: MemoryCreate) -> Memory: ...
    def remember_memory(self, data: MemoryCreate) -> MemoryWriteResult: ...
    def search_similar(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[Memory]: ...
    def search_memories(self, query: str, category: str | None = None) -> list[Memory]: ...
    def get_all_memories(self) -> list[Memory]: ...
    def get_top_memories(self, limit: int = 5) -> list[Memory]: ...
    def get_memory(self, memory_id: int) -> Memory | None: ...
    def update_memory(self, memory_id: int, data: MemoryUpdate) -> Memory | None: ...
    def delete_memory(self, memory_id: int) -> bool: ...
    def content_exists(self, content: str) -> bool: ...
    def mark_recalled(self, memory_ids: list[int]) -> None: ...


def get_memory_store(session: "Session | None" = None) -> MemoryStore:
    """Return the configured memory-store implementation.

    Kept as a factory rather than a module singleton so request paths and
    tests retain the repository's current session ownership semantics.
    """
    from app.memory.repository import MemoryRepository

    return MemoryRepository(session=session)
