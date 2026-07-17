"""Tests for agent tool functions."""

from datetime import datetime

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.tools import (
    calculate_tool,
    create_event_tool,
    forget_fact_tool,
    list_events_tool,
    recall_facts_tool,
    remember_fact_tool,
    search_events_tool,
    timezone_tool,
    weather_query_tool,
)
from app.schedule.database import init_db


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure an in-memory SQLite database is used for tool tests."""
    import app.config

    # Use in-memory database (must be set before engine is created)
    app.config.settings.database_url = "sqlite:///:memory:"

    # Recreate engine + sessionmaker so they point at the in-memory DB
    from app.schedule import database as db_module

    db_module.engine = create_engine("sqlite:///:memory:")
    db_module.SessionLocal = sessionmaker(bind=db_module.engine)
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
            {
                "content": "用户叫张三，在北京做程序员",
                "category": "personal_info",
                "importance": 0.8,
            }
        )
        assert "已记住" in result
        assert "张三" in result

    def test_remember_narrative_content(self):
        """Should store full narrative, not just keywords."""
        result = remember_fact_tool.invoke(
            {
                "content": "用户最近开始学吉他，已经报班上课一周了，感觉挺好玩的",
                "category": "preference",
            }
        )
        assert "已记住" in result
        assert "吉他" in result


class TestRecallFactsTool:
    def test_recall_existing(self):
        remember_fact_tool.invoke(
            {"content": "用户喜欢喝美式咖啡", "category": "preference"}
        )
        result = recall_facts_tool.invoke({"query": "喜欢"})
        assert "找到" in result
        assert "美式咖啡" in result
        assert "[ID:" in result

    def test_recall_no_results(self):
        result = recall_facts_tool.invoke({"query": "zzzznonexistent"})
        assert "没有找到" in result

    def test_recall_with_category(self):
        remember_fact_tool.invoke(
            {"content": "用户想今年学会日语", "category": "goal"}
        )
        result = recall_facts_tool.invoke({"query": "日语", "category": "goal"})
        assert "找到" in result
        result_wrong_cat = recall_facts_tool.invoke(
            {"query": "日语", "category": "preference"}
        )
        assert "没有找到" in result_wrong_cat


class TestForgetFactTool:
    def test_forget_existing(self):
        # Create a memory first, then forget it by ID
        create_result = remember_fact_tool.invoke(
            {"content": "临时数据"}
        )
        # Extract memory ID from the response isn't easy here,
        # so let's use the repository directly to get the ID
        from app.memory.repository import MemoryRepository
        repo = MemoryRepository()
        mems = repo.search_memories("临时数据")
        assert len(mems) >= 1
        mem_id = mems[0].id
        result = forget_fact_tool.invoke({"memory_id": mem_id})
        assert "已删除" in result

    def test_forget_nonexistent(self):
        result = forget_fact_tool.invoke({"memory_id": 999})
        assert "没有找到" in result


class TestWeatherQueryTool:
    def test_weather_with_fallback(self, monkeypatch):
        """The agent tool delegates to the weather client without real network I/O."""
        monkeypatch.setattr(
            "app.agent.tools.get_weather",
            lambda city: f"{city} 当前天气：20°C",
        )
        result = weather_query_tool.invoke({"city": "Beijing"})
        assert "Beijing" in result
        assert "°C" in result

    def test_weather_tokyo(self, monkeypatch):
        monkeypatch.setattr(
            "app.agent.tools.get_weather",
            lambda city: f"{city} 当前天气：21°C",
        )
        result = weather_query_tool.invoke({"city": "Tokyo"})
        assert "Tokyo" in result
        assert "°C" in result


class TestCalculateTool:
    def test_simple_addition(self):
        result = calculate_tool.invoke({"expression": "3+5"})
        assert "8" in result

    def test_complex_expression(self):
        result = calculate_tool.invoke({"expression": "(3+5)*12"})
        assert "96" in result

    def test_division_by_zero(self):
        result = calculate_tool.invoke({"expression": "1/0"})
        assert "无法计算" in result

    def test_unit_conversion_km_to_mi(self):
        result = calculate_tool.invoke({"expression": "10", "from_unit": "公里", "to_unit": "英里"})
        assert "6.21" in result.replace("×", "x")

    def test_unit_conversion_c_to_f(self):
        result = calculate_tool.invoke({"expression": "100", "from_unit": "摄氏度", "to_unit": "华氏度"})
        assert "212" in result

    def test_unit_conversion_kg_to_jin(self):
        result = calculate_tool.invoke({"expression": "5", "from_unit": "公斤", "to_unit": "斤"})
        assert "10" in result

    def test_unsupported_expression(self):
        result = calculate_tool.invoke({"expression": "__import__('os')"})
        assert "不支持" in result or "无法计算" in result


class TestTimezoneTool:
    def test_uses_runtime_configured_timezone(self, monkeypatch):
        import app.agent.tools as tools_module

        monkeypatch.setattr(tools_module.settings, "timezone", "Asia/Tokyo")
        assert tools_module._now().tzinfo.zone == "Asia/Tokyo"

    def test_london_current_time(self):
        result = timezone_tool.invoke({"target_timezone": "Europe/London"})
        assert "🕐" in result
        assert "London" in result or "伦敦" in result

    def test_tokyo_current_time(self):
        result = timezone_tool.invoke({"target_timezone": "Asia/Tokyo"})
        assert "🕐" in result
        assert "Tokyo" in result or "东京" in result

    def test_chinese_alias(self):
        result = timezone_tool.invoke({"target_timezone": "伦敦"})
        assert "🕐" in result
        assert "Europe/London" in result

    def test_invalid_timezone(self):
        result = timezone_tool.invoke({"target_timezone": "火星"})
        assert "无法识别" in result

    def test_with_time_str(self):
        result = timezone_tool.invoke({"target_timezone": "Asia/Tokyo", "time_str": "15:00"})
        assert "🕐" in result
        assert "15" in result or "16" in result or "14" in result
