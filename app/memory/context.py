"""Inject relevant memories into the system prompt via RAG.

Parallels ``app.schedule.notifier.drain_notifications()`` — retrieves the
most semantically relevant memories and formats them for the system prompt.

Because the system prompt is built *before* seeing the user's message, we
inject a mix of:
  1. High-importance memories (importance >= 0.8)
  2. Most recent N memories

The deep semantic search happens inside ``recall_facts_tool`` at query time.
"""

from app.memory.repository import MemoryRepository

_CATEGORY_LABELS: dict[str, str] = {
    "personal_info": "个人信息",
    "preference": "偏好习惯",
    "goal": "目标计划",
    "note": "笔记",
    "general": "其他",
}

_MAX_CONTEXT_MEMORIES = 5  # keep system-prompt token count reasonable


def get_memory_context() -> str | None:
    """Build a formatted block of important + recent memories.

    Returns ``None`` when there are no memories yet.
    """
    repo = MemoryRepository()
    all_mems = repo.get_all_memories()
    if not all_mems:
        return None

    # High-importance first, then recent
    high_importance = [m for m in all_mems if m.importance >= 0.8]
    recent = [m for m in all_mems if m.importance < 0.8]
    selected = (high_importance + recent)[:_MAX_CONTEXT_MEMORIES]

    lines: list[str] = []
    for m in selected:
        label = _CATEGORY_LABELS.get(m.category, m.category)
        lines.append(f"  [{label}] {m.content}")

    return "\n".join(lines)
