"""Prompt-memory cache behavior tests."""

from app.memory import context
from app.memory.models import MemoryCreate, MemoryUpdate


def test_context_cache_is_invalidated_after_explicit_reset(monkeypatch):
    class Memory:
        category = "preference"
        content = "用户喜欢简洁回复"

    class FirstRepository:
        def get_top_memories(self, limit):
            assert limit == 5
            return [Memory()]

    monkeypatch.setattr(context, "get_memory_store", FirstRepository)
    context.invalidate_memory_context()
    assert "简洁回复" in context.get_memory_context()

    class SecondRepository:
        def get_top_memories(self, limit):
            return []

    monkeypatch.setattr(context, "get_memory_store", SecondRepository)
    # Without invalidation this would return the stale first result for 30 seconds.
    assert "简洁回复" in context.get_memory_context()
    context.invalidate_memory_context()
    assert context.get_memory_context() is None


def test_memory_writes_invalidate_prompt_cache(memory_repo, monkeypatch):
    import app.memory.context as context_module

    calls = []
    monkeypatch.setattr(context_module, "invalidate_memory_context", lambda: calls.append(True))
    created = memory_repo.create_memory(MemoryCreate(content="测试记忆"))
    assert created.id is not None
    assert memory_repo.update_memory(created.id, MemoryUpdate(importance=0.8))
    assert memory_repo.delete_memory(created.id) is True
    assert calls == [True, True, True]
