"""LangChain tool definitions for schedule CRUD."""

from datetime import datetime

import re

import dateparser
import pytz
from langchain_core.tools import tool

from app.config import settings
from app.memory.models import MemoryCreate
from app.memory.repository import MemoryRepository
from app.schedule.models import EventCreate, EventUpdate
from app.schedule.repository import ScheduleRepository

repo = ScheduleRepository()
memory_repo = MemoryRepository()
tz = pytz.timezone(settings.timezone)


def _preprocess_chinese_time(text: str) -> str:
    """Convert Chinese time notation (点/分/半) into a format dateparser understands.

    Examples:
        明天下午3点      → 明天下午3:00
        明天下午3点半    → 明天下午3:30
        明天下午3点15分  → 明天下午3:15
    """
    # 替换 "X点半" → "X:30"
    text = re.sub(r"(\d+)\s*点半", r"\1:30", text)
    # 替换 "X点Y分" → "X:Y"
    text = re.sub(r"(\d+)\s*点\s*(\d+)\s*分", r"\1:\2", text)
    # 替换 "X点" → "X:00" (only if no : already present)
    text = re.sub(r"(\d+)\s*点(?!\d)", r"\1:00", text)
    return text


def _parse_time(text: str) -> datetime | None:
    """Parse a Chinese or English relative/absolute time string."""
    processed = _preprocess_chinese_time(text)
    parsed = dateparser.parse(
        processed,
        languages=["zh", "en"],
        settings={"TIMEZONE": settings.timezone, "TO_TIMEZONE": settings.timezone},
    )
    return parsed


def _now() -> datetime:
    return datetime.now(tz)


# ── Tools ────────────────────────────────────────────────────────────


@tool
def create_event_tool(
    title: str,
    start_time: str,
    end_time: str | None = None,
    description: str = "",
    priority: str = "normal",
) -> str:
    """创建新的日程事件。Create a new schedule event.

    当用户说"加日程""添加日程""安排会议""帮我记一下""明天我有..."
    等表达时使用。时间可以用中文相对日期，例如"明天下午3点""后天上午10点"。

    Args:
        title: 事件标题 / Event title (required)
        start_time: 开始时间 / Start time. 支持"YYYY-MM-DD HH:MM"格式或中文自然语言（如"明天下午3点"）
        end_time: 结束时间 / Optional end time (可选)，格式同 start_time
        description: 事件描述 / Optional description (可选)
        priority: 优先级 / Priority: "low", "normal", "high" (默认 "normal")

    Returns:
        创建结果确认字符串
    """
    parsed_start = _parse_time(start_time)
    if parsed_start is None:
        return f"❌ 无法解析开始时间：{start_time}。请提供具体时间，如'明天下午3点'或'2026-06-14 15:00'。"

    parsed_end = None
    if end_time:
        parsed_end = _parse_time(end_time)

    event = repo.create_event(
        EventCreate(
            title=title,
            start_time=parsed_start,
            end_time=parsed_end,
            description=description,
            priority=priority,
        )
    )
    return (
        f"✅ 已创建日程：**{event.title}**\n"
        f"   📅 {event.start_time.strftime('%Y-%m-%d %H:%M')}"
        + (f" → {parsed_end.strftime('%H:%M')}" if parsed_end else "")
        + f"\n   🆔 ID: {event.id}"
    )


@tool
def list_events_tool(date_str: str | None = None) -> str:
    """查询日程事件。List schedule events for a given date.

    当用户问"今天有什么日程""明天的安排""本周有什么""查一下日程"等表达时使用。
    如果不提供日期，默认查询今天的日程。

    Args:
        date_str: 日期 / Date string. 支持"YYYY-MM-DD"格式或中文（如"今天""明天""下周一"）。
                 如果不传，默认为今天。

    Returns:
        日程列表字符串
    """
    target_date = _parse_time(date_str) if date_str else _now()

    events = repo.list_events_by_date(target_date.date())

    if not events:
        return f"📭 {target_date.strftime('%Y年%m月%d日')} 没有日程安排。"

    lines = [f"📋 **{target_date.strftime('%Y年%m月%d日')} 的日程：**"]
    for i, e in enumerate(events, 1):
        time_str = e.start_time.strftime("%H:%M")
        if e.end_time:
            time_str += f" → {e.end_time.strftime('%H:%M')}"
        status_icon = {"pending": "⏳", "completed": "✅", "cancelled": "❌"}.get(
            e.status, "📌"
        )
        lines.append(f"  {i}. {status_icon} **{e.title}**  ({time_str})")
        if e.description:
            lines.append(f"     📝 {e.description[:60]}")

    return "\n".join(lines)


@tool
def update_event_tool(event_id: int, **kwargs) -> str:
    """修改日程事件。Update an existing schedule event.

    当用户说"改到""推迟""修改""重新安排""改时间""改标题"等表达时使用。
    可修改的字段：title（标题）, start_time（开始时间）, end_time（结束时间）,
    description（描述）, status（状态：pending/completed/cancelled）,
    priority（优先级：low/normal/high）, category（分类）。

    Args:
        event_id: 事件 ID (数字)
        **kwargs: 要修改的字段和值。时间字段同样支持中文相对日期。

    Returns:
        修改结果确认字符串
    """
    # Parse time fields if they're strings
    for time_field in ("start_time", "end_time"):
        if time_field in kwargs and isinstance(kwargs[time_field], str):
            parsed = _parse_time(kwargs[time_field])
            if parsed is None:
                return f"❌ 无法解析时间：{kwargs[time_field]}"
            kwargs[time_field] = parsed

    update_data = EventUpdate(**kwargs)
    event = repo.update_event(event_id, update_data)

    if event is None:
        return f"❌ 未找到 ID 为 {event_id} 的日程事件。"

    return f"✅ 已更新日程：**{event.title}** (ID: {event.id})"


@tool
def delete_event_tool(event_id: int) -> str:
    """删除日程事件。Delete a schedule event by its ID.

    当用户说"删除""取消""移除""去掉这个日程"等表达时使用。
    需要提供事件 ID（可在查询结果中看到）。

    Args:
        event_id: 事件 ID (数字)

    Returns:
        删除结果确认字符串
    """
    success = repo.delete_event(event_id)
    if success:
        return f"🗑️ 已删除日程 (ID: {event_id})"
    return f"❌ 未找到 ID 为 {event_id} 的日程事件。"


@tool
def search_events_tool(keyword: str) -> str:
    """搜索日程事件。Search events by keyword in title or description.

    当用户说"找一下xxx""搜索xxx""包含xxx的事件"等表达时使用。

    Args:
        keyword: 搜索关键词

    Returns:
        匹配的日程列表
    """
    events = repo.search_events(keyword)

    if not events:
        return f"🔍 没有找到包含「{keyword}」的日程。"

    lines = [f"🔍 找到 {len(events)} 个包含「{keyword}」的日程："]
    for i, e in enumerate(events, 1):
        lines.append(
            f"  {i}. **{e.title}**  ({e.start_time.strftime('%Y-%m-%d %H:%M')})  [ID: {e.id}]"
        )
    return "\n".join(lines)


@tool
def get_current_datetime_tool() -> str:
    """获取当前日期和时间。Get the current date and time.

    当用户问"现在几点了""今天几号""现在时间"等表达时使用。
    也可以被其他工具间接使用来确定相对日期。

    Returns:
        当前日期时间字符串
    """
    now = _now()
    return now.strftime("%Y-%m-%d %H:%M:%S %A")


# ── Memory Tools ───────────────────────────────────────────────────────


@tool
def remember_fact_tool(key: str, value: str, category: str = "general") -> str:
    """记住关于用户的个人信息。Remember a personal fact about the user.

    当用户分享个人信息、偏好、目标或任何你想记住的信息时**必须**使用此工具。
    例如用户说"我叫小明""我住在北京""我喜欢编程""我想今年学会游泳"等。
    分类说明：personal_info（姓名/职业/住址等个人信息）、preference（喜好/习惯）、
    goal（目标/计划）、note（一般笔记）、general（其他）。

    Args:
        key: 信息关键词（英文或拼音），如 "user_name" "work_company" "preference_coffee" "goal_2026"
        value: 信息内容（可以使用中文）
        category: 分类：personal_info, preference, goal, note, general（默认 general）

    Returns:
        记忆存储确认
    """
    entry = memory_repo.create_memory(
        MemoryCreate(key=key, value=value, category=category, source="chat")
    )
    cat_labels = {
        "personal_info": "个人信息",
        "preference": "偏好",
        "goal": "目标",
        "note": "笔记",
        "general": "其他",
    }
    label = cat_labels.get(category, category)
    return f"🧠 已记住（{label}）：{entry.key} = {entry.value}"


@tool
def recall_facts_tool(query: str, category: str | None = None) -> str:
    """回忆关于用户的个人信息。Recall personal facts about the user.

    当需要根据用户个人背景提供建议或回答问题时使用。
    例如用户问"你还记得我喜欢什么吗""根据我的情况帮我分析""你觉得我应该..."
    此工具会根据关键词搜索记忆，不仅限于精确匹配。

    Args:
        query: 搜索关键词，如"喜欢""工作""目标""2026"
        category: 可选分类过滤：personal_info, preference, goal, note, general

    Returns:
        匹配的记忆列表
    """
    results = memory_repo.search_memories(query, category=category)
    if not results:
        return f"🔍 没有找到关于「{query}」的记忆。"

    cat_labels = {
        "personal_info": "个人信息",
        "preference": "偏好",
        "goal": "目标",
        "note": "笔记",
        "general": "其他",
    }
    lines = [f"🔍 找到 {len(results)} 条关于「{query}」的记忆："]
    for i, m in enumerate(results, 1):
        label = cat_labels.get(m.category, m.category)
        lines.append(f"  {i}. [{label}] {m.key} = {m.value}")
    return "\n".join(lines)


@tool
def forget_fact_tool(key: str) -> str:
    """删除关于用户的个人信息。Forget/delete a personal fact.

    当用户表示某条记忆不再准确或要求删除时使用。

    Args:
        key: 要删除的信息关键词（remember_fact_tool 中使用的 key）

    Returns:
        删除确认
    """
    success = memory_repo.delete_memory_by_key(key)
    if success:
        return f"🗑️ 已删除关于「{key}」的记忆。"
    return f"❌ 没有找到关于「{key}」的记忆。"


# ── Tool Registry ────────────────────────────────────────────────────

ALL_TOOLS = [
    create_event_tool,
    list_events_tool,
    update_event_tool,
    delete_event_tool,
    search_events_tool,
    get_current_datetime_tool,
    remember_fact_tool,
    recall_facts_tool,
    forget_fact_tool,
]
