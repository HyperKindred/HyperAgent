"""Inject relevant memories into the system prompt via RAG.

Parallels ``app.schedule.notifier.drain_notifications()`` — retrieves the
most semantically relevant memories and formats them for the system prompt.

Because the system prompt is built *before* seeing the user's message, we
inject a small set ranked by user importance, bounded freshness, and actual
recall history.

The deep semantic search happens inside ``recall_facts_tool`` at query time.
"""

import time

from app.memory.store import get_memory_store

_CATEGORY_LABELS: dict[str, str] = {
    "personal_info": "个人信息",
    "preference": "偏好习惯",
    "goal": "目标计划",
    "note": "笔记",
    "general": "其他",
}

_MAX_CONTEXT_MEMORIES = 5  # keep system-prompt token count reasonable

# Simple TTL cache so the system prompt doesn't hit the DB every turn.
_cache: dict = {}
_CACHE_TTL = 30  # seconds


def invalidate_memory_context() -> None:
    """Clear the prompt cache after a memory write or delete."""
    _cache.clear()

def get_memory_context() -> str | None:
    """Build a formatted block of important + recent memories.

    Results are cached for ``_CACHE_TTL`` seconds to avoid hitting the
    database on every agent turn.  Returns ``None`` when there are no
    memories yet.
    """
    global _cache
    now = time.time()
    if _cache and now - _cache.get("_ts", 0) < _CACHE_TTL:
        return _cache.get("value")

    # Query only the top memories instead of loading everything
    repo = get_memory_store()
    selected = repo.get_top_memories(limit=_MAX_CONTEXT_MEMORIES)
    if not selected:
        _cache = {"_ts": now, "value": None}
        return None

    lines: list[str] = []
    for m in selected:
        label = _CATEGORY_LABELS.get(m.category, m.category)
        lines.append(f"  [{label}] {m.content}")

    result = "\n".join(lines)
    _cache = {"_ts": now, "value": result}
    return result
