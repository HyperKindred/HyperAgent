"""Tests for MemoryRepository CRUD + semantic search."""

from datetime import timedelta

import pytest

from app.memory.models import MemoryCreate, MemoryUpdate
from app.memory.embeddings import EmbeddingResult
from app.utils.time import now as utc_now


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

    def test_embedding_failure_does_not_log_memory_content(
        self, memory_repo, monkeypatch, caplog
    ):
        def fail_embedding(_text):
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr("app.memory.repository.get_embedding_result", fail_embedding)
        secret_content = "用户的私密记忆内容"
        memory_repo.create_memory(MemoryCreate(content=secret_content))
        assert secret_content not in caplog.text

    def test_agent_memory_write_consolidates_high_similarity_fact(
        self, memory_repo, monkeypatch
    ):
        result = EmbeddingResult(
            vector=[1.0, 0.0],
            model="test-model",
            dimensions=2,
            fingerprint="test-provider",
            source="separate",
        )
        monkeypatch.setattr("app.memory.repository.get_embedding_result", lambda _text: result)

        first = memory_repo.remember_memory(
            MemoryCreate(content="用户喜欢喝咖啡", category="general", importance=0.5)
        )
        second = memory_repo.remember_memory(
            MemoryCreate(content="用户偏爱咖啡", category="preference", importance=0.8)
        )

        assert first.created is True
        assert second.created is False
        assert second.entry.id == first.entry.id
        assert second.entry.importance == 0.8
        assert second.entry.category == "preference"
        assert len(memory_repo.get_all_memories()) == 1


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


class TestUpdateMemory:
    def test_update_memory_fields(self, memory_repo):
        created = memory_repo.create_memory(
            MemoryCreate(content="旧内容", category="general", importance=0.3)
        )
        updated = memory_repo.update_memory(
            created.id,
            MemoryUpdate(content="新内容", category="preference", importance=0.8),
        )
        assert updated is not None
        assert updated.content == "新内容"
        assert updated.category == "preference"
        assert updated.importance == 0.8

    def test_update_nonexistent_memory(self, memory_repo):
        assert memory_repo.update_memory(999, MemoryUpdate(content="不存在")) is None

    def test_exact_content_check(self, memory_repo):
        memory_repo.create_memory(MemoryCreate(content="唯一记忆"))
        assert memory_repo.content_exists("唯一记忆") is True
        assert memory_repo.content_exists("另一个记忆") is False

    def test_mark_recalled_tracks_unique_memories(self, memory_repo):
        first = memory_repo.create_memory(MemoryCreate(content="第一条记忆"))
        second = memory_repo.create_memory(MemoryCreate(content="第二条记忆"))
        memory_repo.mark_recalled([first.id, first.id])

        refreshed_first = memory_repo.get_memory(first.id)
        refreshed_second = memory_repo.get_memory(second.id)
        assert refreshed_first.recall_count == 1
        assert refreshed_first.last_recalled_at is not None
        assert refreshed_second.recall_count == 0
        assert refreshed_second.last_recalled_at is None

    def test_prompt_ranking_gently_decays_stale_low_priority_memory(
        self, memory_repo, session
    ):
        stale = memory_repo.create_memory(
            MemoryCreate(content="很久以前的低优先级记忆", importance=0.5)
        )
        current = memory_repo.create_memory(
            MemoryCreate(content="近期重要事项", importance=0.7)
        )
        stale.updated_at = utc_now() - timedelta(days=730)
        stale.last_recalled_at = None
        session.commit()

        top = memory_repo.get_top_memories(limit=1)
        assert [memory.id for memory in top] == [current.id]


class TestGetAllMemories:
    def test_get_all(self, memory_repo):
        memory_repo.create_memory(MemoryCreate(content="记忆A"))
        memory_repo.create_memory(MemoryCreate(content="记忆B"))
        all_mems = memory_repo.get_all_memories()
        assert len(all_mems) >= 2
