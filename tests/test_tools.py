"""Tests for agent tool functions."""

from datetime import datetime

import pytest

from app.agent.tools import (
    create_event_tool,
    forget_fact_tool,
    list_events_tool,
    recall_facts_tool,
    remember_fact_tool,
    search_events_tool,
)
from app.schedule.database import init_db


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure database tables exist before tests run."""
    # Use an in-memory SQLite via config override
    import app.config
    app.config.settings.database_url = "sqlite:///:memory:"
    init_db()


class TestCreateEventTool:
    def test_create_with_chinese_time(self):
        """Should parse '明天下午3点' style inputs."""
        result = create_event_tool.invoke(
            {
                "title": "开会",
                "start_time": "明天下午3点",
                "description": "项目讨论",
            }
        )
        assert "已创建日程" in result
        assert "开会" in result

    def test_create_with_absolute_time(self):
        result = create_event_tool.invoke(
            {
                "title": "面试",
                "start_time": "2026-06-20 10:00",
            }
        )
        assert "已创建日程" in result


class TestListEventsTool:
    def test_list_today(self):
        """Should return a string (either events listed or empty message)."""
        result = list_events_tool.invoke({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_list_with_date(self):
        result = list_events_tool.invoke({"date_str": "2026-06-14"})
        assert isinstance(result, str)


class TestSearchEventsTool:
    def test_search_no_results(self):
        result = search_events_tool.invoke({"keyword": "zzzznonexistent"})
        assert "没有找到" in result

    def test_search_with_data(self, repo):
        """After creating an event, searching for its title should find it."""
        from app.schedule.models import EventCreate
        repo.create_event(
            EventCreate(
                title="UniqueMeeting",
                start_time=datetime(2026, 7, 1, 10, 0),
            )
        )
        result = search_events_tool.invoke({"keyword": "UniqueMeeting"})
        assert "找到" in result
        assert "UniqueMeeting" in result


class TestRememberFactTool:
    def test_remember_basic(self):
        result = remember_fact_tool.invoke(
            {"key": "user_name", "value": "张三", "category": "personal_info"}
        )
        assert "已记住" in result
        assert "张三" in result

    def test_remember_upsert(self):
        """Same key should update value, not create duplicate."""
        r1 = remember_fact_tool.invoke(
            {"key": "preference_coffee", "value": "喜欢美式"}
        )
        r2 = remember_fact_tool.invoke(
            {"key": "preference_coffee", "value": "现在喜欢拿铁了"}
        )
        assert "已记住" in r2
        assert "拿铁" in r2


class TestRecallFactsTool:
    def test_recall_existing(self):
        remember_fact_tool.invoke(
            {"key": "test_recall", "value": "测试数据", "category": "general"}
        )
        result = recall_facts_tool.invoke({"query": "测试"})
        assert "找到" in result
        assert "测试数据" in result

    def test_recall_no_results(self):
        result = recall_facts_tool.invoke({"query": "zzzznonexistent"})
        assert "没有找到" in result

    def test_recall_with_category(self):
        remember_fact_tool.invoke(
            {"key": "goal_2026", "value": "学日语", "category": "goal"}
        )
        result = recall_facts_tool.invoke({"query": "日语", "category": "goal"})
        assert "找到" in result
        result_wrong_cat = recall_facts_tool.invoke(
            {"query": "日语", "category": "preference"}
        )
        assert "没有找到" in result_wrong_cat


class TestForgetFactTool:
    def test_forget_existing(self):
        remember_fact_tool.invoke({"key": "temp_key", "value": "临时数据"})
        result = forget_fact_tool.invoke({"key": "temp_key"})
        assert "已删除" in result

    def test_forget_nonexistent(self):
        result = forget_fact_tool.invoke({"key": "no_such_key"})
        assert "没有找到" in result
