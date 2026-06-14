"""Tests for MemoryRepository CRUD + semantic search."""

import pytest

from app.memory.models import MemoryCreate


class TestCreateMemory:
    def test_create_basic(self, memory_repo):
        mem = memory_repo.create_memory(
            MemoryCreate(
                content="用户叫张三，在北京做程序员",
                category="personal_info",
                importance=0.8,
            )
        )
        assert mem.id is not None
        assert "张三" in mem.content
        assert mem.category == "personal_info"
        assert mem.importance == 0.8
        assert mem.source == "chat"

    def test_create_defaults(self, memory_repo):
        mem = memory_repo.create_memory(
            MemoryCreate(content="测试默认值")
        )
        assert mem.category == "general"
        assert mem.importance == 0.5

    def test_create_multiple(self, memory_repo):
        m1 = memory_repo.create_memory(MemoryCreate(content="第一条"))
        m2 = memory_repo.create_memory(MemoryCreate(content="第二条"))
        m3 = memory_repo.create_memory(MemoryCreate(content="第三条"))
        assert m1.id != m2.id
        assert m2.id != m3.id
        assert m1.id != m3.id


class TestGetMemory:
    def test_get_by_id(self, memory_repo):
        created = memory_repo.create_memory(
            MemoryCreate(content="测试数据")
        )
        fetched = memory_repo.get_memory(created.id)
        assert fetched is not None
        assert fetched.content == "测试数据"

    def test_get_nonexistent(self, memory_repo):
        assert memory_repo.get_memory(999) is None


class TestListByCategory:
    def test_list_category(self, memory_repo):
        memory_repo.create_memory(
            MemoryCreate(content="叫李四", category="personal_info")
        )
        memory_repo.create_memory(
            MemoryCreate(content="在北京", category="personal_info")
        )
        memory_repo.create_memory(
            MemoryCreate(content="喜欢编程", category="preference")
        )
        results = memory_repo.list_by_category("personal_info")
        assert len(results) == 2

    def test_list_empty_category(self, memory_repo):
        assert len(memory_repo.list_by_category("goal")) == 0


class TestDeleteMemory:
    def test_delete_by_id(self, memory_repo):
        created = memory_repo.create_memory(MemoryCreate(content="待删除"))
        assert memory_repo.delete_memory(created.id) is True
        assert memory_repo.get_memory(created.id) is None

    def test_delete_nonexistent(self, memory_repo):
        assert memory_repo.delete_memory(999) is False


class TestGetAllMemories:
    def test_get_all(self, memory_repo):
        memory_repo.create_memory(MemoryCreate(content="记忆A"))
        memory_repo.create_memory(MemoryCreate(content="记忆B"))
        all_mems = memory_repo.get_all_memories()
        assert len(all_mems) >= 2
