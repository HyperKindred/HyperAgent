"""User-facing memory management and portable JSON backup endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory.models import MemoryCreate, MemoryResponse, MemoryUpdate
from app.memory.store import get_memory_store

router = APIRouter(prefix="/memories", tags=["memory"])


class MemoryImportItem(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    category: str = Field(default="general", min_length=1, max_length=50)
    importance: float = Field(default=0.5, ge=0, le=1)
    source: str = Field(default="import", max_length=50)


class MemoryImportRequest(BaseModel):
    memories: list[MemoryImportItem] = Field(min_length=1, max_length=200)
    mode: Literal["skip_duplicates", "allow_duplicates"] = "skip_duplicates"


@router.get("", response_model=list[MemoryResponse])
def list_memories(q: str = "", category: str | None = None, limit: int = 200):
    """List memories, or perform a keyword search when ``q`` is supplied."""
    repo = get_memory_store()
    limit = max(1, min(limit, 200))
    entries = repo.search_memories(q, category) if q.strip() else repo.get_all_memories()
    if category and not q.strip():
        entries = [entry for entry in entries if entry.category == category]
    return [MemoryResponse.model_validate(entry) for entry in entries[:limit]]


@router.post("", response_model=MemoryResponse, status_code=201)
def create_memory(data: MemoryCreate):
    return MemoryResponse.model_validate(get_memory_store().create_memory(data))


@router.put("/{memory_id}", response_model=MemoryResponse)
def update_memory(memory_id: int, data: MemoryUpdate):
    entry = get_memory_store().update_memory(memory_id, data)
    if entry is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return MemoryResponse.model_validate(entry)


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: int):
    if not get_memory_store().delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在")


@router.get("/export")
def export_memories():
    """Export narrative data only; vectors are provider-specific and omitted."""
    memories = get_memory_store().get_all_memories()
    return {
        "format": "hyperagent-memory-backup",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "memories": [
            {
                "content": entry.content,
                "category": entry.category,
                "importance": entry.importance,
                "source": entry.source,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in memories
        ],
    }


@router.post("/import")
def import_memories(body: MemoryImportRequest):
    """Import portable narrative records, skipping exact duplicates by default."""
    repo = get_memory_store()
    imported = 0
    skipped = 0
    for item in body.memories:
        content = item.content.strip()
        if body.mode == "skip_duplicates" and repo.content_exists(content):
            skipped += 1
            continue
        repo.create_memory(
            MemoryCreate(
                content=content,
                category=item.category.strip(),
                importance=item.importance,
                source="import",
            )
        )
        imported += 1
    return {"imported": imported, "skipped": skipped}
