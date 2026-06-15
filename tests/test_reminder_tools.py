"""Tests for reminder tools (create_reminder_tool, list_reminders_tool, delete_reminder_tool).

Uses a temporary file-based SQLite database to avoid in-memory connection-pooling issues.
"""

import tempfile

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.agent.tools import create_reminder_tool, delete_reminder_tool, list_reminders_tool
from app.reminder.repository import ReminderRepository
from app.schedule.database import Base


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Use a temporary file-based SQLite for tool tests (avoids :memory: pooling issues)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)

    # Patch SessionLocal at module level (app.reminder.repository has a module-level import)
    import app.reminder.repository as repo_module

    monkeypatch.setattr(repo_module, "SessionLocal", SessionLocal)

    # Also patch app.schedule.database for any function-level imports (notifier, etc.)
    import app.schedule.database as db_module

    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)

    # Create all tables
    Base.metadata.create_all(engine)

    # Verify
    tables = inspect(engine).get_table_names()
    assert "reminders" in tables, f"reminders missing! Got: {tables}"

    yield

    # Cleanup: close all connections and delete the temp file
    engine.dispose()
    import os
    try:
        os.unlink(db_path)
    except OSError:
        pass


class TestCreateReminderTool:
    def test_create_with_future_time(self):
        result = create_reminder_tool.invoke(
            {"title": "test_water", "trigger_time": "+5分钟", "description": "drink water"}
        )
        assert "⏰" in result or "已创建提醒" in result
        assert "test_water" in result

    def test_create_with_recurring(self):
        result = create_reminder_tool.invoke(
            {
                "title": "test_standup",
                "trigger_time": "明天上午9点",
                "recurring": "0 9 * * 1-5",
            }
        )
        assert "⏰" in result or "已创建提醒" in result
        assert "test_standup" in result


class TestListRemindersTool:
    def test_list_empty(self):
        result = list_reminders_tool.invoke({})
        assert "📭" in result or "没有" in result

    def test_list_pending(self):
        create_reminder_tool.invoke({"title": "test_item", "trigger_time": "+10分钟"})
        result = list_reminders_tool.invoke({"status": "pending"})
        assert "test_item" in result
        assert "⏳" in result or "待触发" in result


class TestDeleteReminderTool:
    def test_delete_existing(self):
        create_reminder_tool.invoke({"title": "test_delete_me", "trigger_time": "+10分钟"})

        repo = ReminderRepository()
        pending = [r for r in repo.list_pending() if r.title == "test_delete_me"]
        assert len(pending) >= 1

        result = delete_reminder_tool.invoke({"reminder_id": pending[0].id})
        assert "🗑️" in result or "已删除" in result

    def test_delete_nonexistent(self):
        result = delete_reminder_tool.invoke({"reminder_id": 99999})
        assert "❌" in result or "未找到" in result
