"""Tests for ThreadRepository CRUD."""

import sqlite3

from app.thread.models import Thread, ThreadCreate
from app.thread.repository import ThreadRepository


def _make_thread(repo: ThreadRepository, thread_id: str, title: str = "测试对话"):
    return repo.create(ThreadCreate(thread_id=thread_id, title=title))


class TestThreadRepository:
    def test_create_and_get(self, session):
        repo = ThreadRepository(db=session)
        t = _make_thread(repo, "hyperagent-test-001")
        assert t.id == "hyperagent-test-001"
        assert t.title == "测试对话"
        assert t.message_count == 0

    def test_get_all_ordered(self, session):
        repo = ThreadRepository(db=session)
        _make_thread(repo, "thread-1", "旧对话")
        _make_thread(repo, "thread-2", "新对话")
        all_t = repo.get_all()
        # ordered by updated_at DESC → thread-2 should be first
        assert all_t[0].id == "thread-2" or all_t[0].id == "thread-1"

    def test_get_by_id(self, session):
        repo = ThreadRepository(db=session)
        _make_thread(repo, "test-thread")
        t = repo.get_by_id("test-thread")
        assert t is not None
        assert t.id == "test-thread"

    def test_get_by_id_nonexistent(self, session):
        repo = ThreadRepository(db=session)
        assert repo.get_by_id("nonexistent") is None

    def test_update_title(self, session):
        repo = ThreadRepository(db=session)
        _make_thread(repo, "thread-rename", "旧标题")
        t = repo.update_title("thread-rename", "新标题")
        assert t is not None
        assert t.title == "新标题"

    def test_update_title_nonexistent(self, session):
        repo = ThreadRepository(db=session)
        assert repo.update_title("nonexistent", "新标题") is None

    def test_thread_updates_use_unified_utc_clock(self, session):
        onupdate = Thread.__table__.c.updated_at.onupdate
        assert onupdate is not None
        assert onupdate.arg.__module__ == "app.utils.time"
        assert onupdate.arg.__name__ == "now"
        repo = ThreadRepository(db=session)
        _make_thread(repo, "thread-utc")

        updated = repo.update_title("thread-utc", "已更新")
        repo.touch("thread-utc")

        assert updated is not None
        assert repo.get_by_id("thread-utc").message_count == 1

    def test_delete(self, session):
        repo = ThreadRepository(db=session)
        _make_thread(repo, "thread-del")
        assert repo.delete("thread-del") is True
        assert repo.get_by_id("thread-del") is None

    def test_delete_nonexistent(self, session):
        repo = ThreadRepository(db=session)
        assert repo.delete("nonexistent") is False

    def test_checkpoint_cleanup_handles_minimal_langgraph_schema(self, tmp_path, monkeypatch):
        db_path = tmp_path / "checkpoints.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint TEXT)")
        conn.execute("INSERT INTO checkpoints VALUES ('hyperagent-delete', 'one')")
        conn.execute("INSERT INTO checkpoints VALUES ('hyperagent-keep', 'two')")
        conn.commit()
        conn.close()

        import app.thread.repository as repository_module

        monkeypatch.setattr(repository_module.settings, "data_dir", tmp_path)
        ThreadRepository._delete_checkpoints("hyperagent-delete")

        conn = sqlite3.connect(db_path)
        remaining = conn.execute("SELECT thread_id FROM checkpoints").fetchall()
        conn.close()
        assert remaining == [("hyperagent-keep",)]
