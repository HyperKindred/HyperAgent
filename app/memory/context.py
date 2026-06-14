"""Inject stored memories into the system prompt so the agent sees known facts.

Parallels ``app.schedule.notifier.drain_notifications()`` — fetches all
memories and formats them as a text block for the system prompt.
"""

from app.memory.repository import MemoryRepository

# Labels used in the formatted output
_CATEGORY_LABELS: dict[str, str] = {
    "personal_info": "个人信息",
    "preference": "偏好习惯",
    "goal": "目标计划",
    "note": "笔记",
    "general": "其他",
}

# Display order for categories
_CATEGORY_ORDER: list[str] = [
    "personal_info",
    "preference",
    "goal",
    "note",
    "general",
]


def get_memory_context() -> str | None:
    """Build a formatted block of all known user memories.

    Returns ``None`` when there are no memories yet (so callers can skip
    the block entirely).
    """
    repo = MemoryRepository()
    memories = repo.get_all_memories()
    if not memories:
        return None

    # Group by category
    grouped: dict[str, list] = {}
    for m in memories:
        grouped.setdefault(m.category, []).append(m)

    lines: list[str] = []
    for cat in _CATEGORY_ORDER:
        items = grouped.get(cat)
        if not items:
            continue
        label = _CATEGORY_LABELS.get(cat, cat)
        lines.append(f"  [{label}]")
        for item in items:
            lines.append(f"    • {item.key}: {item.value}")

    return "\n".join(lines)
