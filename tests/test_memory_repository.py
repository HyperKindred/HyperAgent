"""Tests for MemoryRepository CRUD operations (upsert-by-key semantics)."""

import pytest

from app.memory.models import MemoryCreate


class TestCreateMemory:
    def test_create_basic(self, memory_repo):
        mem = memory_repo.create_memory(
            MemoryCreate(key="user_name", value="张三", category="personal_info")
        )
        assert mem.id is not None
        assert mem.key == "user_name"
        assert mem.value == "张三"
        assert mem.category == "personal_info"
        assert mem.source == "chat"

    def test_create_default_category(self, memory_repo):
        mem = memory_repo.create_memory(
            MemoryCreate(key="test_note", value="随便记一下")
        )
        assert mem.category == "general"
        assert mem.key == "test_note"

    def test_upsert_same_key_updates_value(self, memory_repo):
        # Create first
        m1 = memory_repo.create_memory(
            MemoryCreate(key="preference_coffee", value="喜欢美式")
        )
        first_id = m1.id

        # Upsert with same key but different value
        m2 = memory_repo.create_memory(
            MemoryCreate(key="preference_coffee", value="现在喜欢拿铁了")
        )

        # Same record, updated value
        assert m2.id == first_id
        assert m2.value == "现在喜欢拿铁了"

    def test_upsert_same_key_updates_category(self, memory_repo):
        memory_repo.create_memory(
            MemoryCreate(key="test_key", value="test", category="general")
        )
        m2 = memory_repo.create_memory(
            MemoryCreate(key="test_key", value="test", category="preference")
        )
        assert m2.category == "preference"


class TestGetMemory:
    def test_get_by_key_existing(self, memory_repo):
        memory_repo.create_memory(
            MemoryCreate(key="user_job", value="软件工程师")
        )
        mem = memory_repo.get_memory_by_key("user_job")
        assert mem is not None
        assert mem.value == "软件工程师"

    def test_get_by_key_nonexistent(self, memory_repo):
        assert memory_repo.get_memory_by_key("nonexistent") is None


class TestSearchMemories:
    def test_search_by_key(self, memory_repo, sample_memories):
        results = memory_repo.search_memories("preference")
        assert len(results) == 1
        assert results[0].key == "preference_coffee"

    def test_search_by_value(self, memory_repo, sample_memories):
        results = memory_repo.search_memories("北京")
        assert len(results) == 1
        assert results[0].value == "北京"

    def test_search_no_match(self, memory_repo):
        assert len(memory_repo.search_memories("不存在的")) == 0

    def test_search_with_category_filter(self, memory_repo, sample_memories):
        results = memory_repo.search_memories("喜欢", category="preference")
        assert len(results) == 1
        results = memory_repo.search_memories("喜欢", category="personal_info")
        assert len(results) == 0


class TestListByCategory:
    def test_list_category(self, memory_repo, sample_memories):
        results = memory_repo.list_by_category("personal_info")
        assert len(results) == 2
        keys = [m.key for m in results]
        assert "user_name" in keys
        assert "user_location" in keys

    def test_list_empty_category(self, memory_repo):
        assert len(memory_repo.list_by_category("goal")) == 0


class TestDeleteMemory:
    def test_delete_by_key(self, memory_repo):
        memory_repo.create_memory(MemoryCreate(key="to_delete", value="删除我"))
        assert memory_repo.delete_memory_by_key("to_delete") is True
        assert memory_repo.get_memory_by_key("to_delete") is None

    def test_delete_by_key_nonexistent(self, memory_repo):
        assert memory_repo.delete_memory_by_key("no_such_key") is False


# ── Fixture ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_memories(memory_repo):
    """Insert several test memories."""
    memory_repo.create_memory(
        MemoryCreate(key="user_name", value="张三", category="personal_info")
    )
    memory_repo.create_memory(
        MemoryCreate(
            key="user_location", value="北京", category="personal_info"
        )
    )
    memory_repo.create_memory(
        MemoryCreate(key="preference_coffee", value="喜欢美式", category="preference")
    )
    return
