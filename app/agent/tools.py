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
from app.web_search.searcher import search_web

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


# ── 错误处理约定 ─────────────────────────────────────────────────
# 用户输入/业务逻辑错误 → return 友好的字符串提示（LLM 可见，可用于回复用户）
# 系统异常（DB 连接失败、API 不可达）→ raise 异常，由 LangGraph 的 ToolNode
#   捕获并返回 ToolMessage 错误，LLM 会看到调用失败并尝试修正。
#
# 注意：两种方式各有用途。return 字符串适合"找不到这个ID"，
# raise 异常适合"时间格式完全无法解析，需要 LLM 重试"。
# ──────────────────────────────────────────────────────────────────


@tool
def create_event_tool(
    title: str,
    start_time: str,
    end_time: str | None = None,
    description: str = "",
    priority: str = "normal",
    remind: bool = False,
) -> str:
    """创建新的日程事件。Create a new schedule event.

    当用户说"加日程""添加日程""安排会议""帮我记一下""明天我有..."
    等表达时使用。时间可以用中文相对日期，例如"明天下午3点""后天上午10点"。

    **关于是否提醒：**
    - 默认不给提醒（remind=False）
    - 如果用户明确说"提醒我""设个提醒""到点叫我"等，传 remind=True
    - 对于"会议""比赛""面试""考试""约了人"等时间敏感的事项，
      主动问用户一句"需要设置提醒吗？"
    - 对于"看电影""跑步""购物""记一下"等随意事项，直接创建无需询问

    Args:
        title: 事件标题 / Event title (required)
        start_time: 开始时间 / Start time. 支持"YYYY-MM-DD HH:MM"格式或中文自然语言（如"明天下午3点"）
        end_time: 结束时间 / Optional end time (可选)，格式同 start_time
        description: 事件描述 / Optional description (可选)
        priority: 优先级 / Priority: "low", "normal", "high" (默认 "normal")
        remind: 是否创建提醒 / Create a reminder (默认 False，需要时由 agent 询问用户后设为 True)

    Returns:
        创建结果确认字符串
    """
    parsed_start = _parse_time(start_time)
    if parsed_start is None:
        raise ValueError(f"无法解析开始时间：{start_time}。请提供具体时间，如‘明天下午3点’或‘2026-06-14 15:00’。")

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

    # ── 自动联动：创建日程的同时创建一个提醒 ─────────────────────
    reminder_note = ""
    now = _now()
    # Ensure parsed_start is timezone-aware for comparison
    reminder_trigger = parsed_start
    if reminder_trigger.tzinfo is None:
        reminder_trigger = reminder_trigger.replace(tzinfo=tz)
    if remind and reminder_trigger > now:
        try:
            from app.reminder.models import ReminderCreate
            from app.reminder.repository import ReminderRepository
            from app.reminder.scheduler import schedule_reminder_job

            reminder_repo = ReminderRepository()
            reminder_data = ReminderCreate(
                title=f"📅 {title}",
                description=description or title,
                trigger_at=parsed_start,
                event_id=event.id,
            )
            reminder = reminder_repo.create(reminder_data)
            schedule_reminder_job(reminder)
            reminder_note = f"\n   ⏰ 已自动设置提醒（触发时间：{parsed_start.strftime('%H:%M')}）"
        except Exception as e:
            reminder_note = f"\n   ⚠️ 提醒设置失败：{e}"

    return (
        f"✅ 已创建日程：**{event.title}**\n"
        f"   📅 {event.start_time.strftime('%Y-%m-%d %H:%M')}"
        + (f" → {parsed_end.strftime('%H:%M')}" if parsed_end else "")
        + f"\n   🆔 ID: {event.id}"
        + reminder_note
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
                raise ValueError(f"无法解析时间：{kwargs[time_field]}。请提供具体时间，如‘明天下午3点’或‘2026-06-14 15:00’。")
            kwargs[time_field] = parsed

    update_data = EventUpdate(**kwargs)
    event = repo.update_event(event_id, update_data)

    if event is None:
        return f"❌ 未找到 ID 为 {event_id} 的日程事件。"

    # ── 同步关联提醒 ─────────────────────────────────────────────
    try:
        from app.reminder.repository import ReminderRepository
        from app.reminder.scheduler import cancel_reminder_job, schedule_reminder_job
        from app.reminder.models import ReminderCreate

        rrepo = ReminderRepository()
        linked = rrepo.get_by_event_id(event_id)

        if linked:
            # 取消旧提醒
            cancel_reminder_job(linked.id)

            if kwargs.get("status") in ("completed", "cancelled"):
                # 日程标记完成/取消 → 删除提醒
                rrepo.delete(linked.id)
            else:
                # 更新提醒标题和/或触发时间
                new_title = f"📅 {kwargs.get('title', linked.title.removeprefix('📅 '))}"
                new_trigger = kwargs.get("start_time", linked.trigger_at)
                # 重建提醒（简单做法：删旧建新）
                rrepo.delete(linked.id)
                new_reminder = rrepo.create(ReminderCreate(
                    title=new_title,
                    description=event.description or event.title,
                    trigger_at=new_trigger,
                    event_id=event.id,
                ))
                schedule_reminder_job(new_reminder)
    except Exception:
        pass

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
        # Also delete linked reminder, if any
        try:
            from app.reminder.repository import ReminderRepository
            from app.reminder.scheduler import cancel_reminder_job

            rrepo = ReminderRepository()
            linked = rrepo.get_by_event_id(event_id)
            if linked:
                cancel_reminder_job(linked.id)
                rrepo.delete(linked.id)
                return f"🗑️ 已删除日程及关联提醒 (ID: {event_id})"
        except Exception:
            pass
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
def remember_fact_tool(
    content: str, category: str = "general", importance: float = 0.5
) -> str:
    """记住重要信息。Save an important memory about the user.

    **必须**在以下场景主动使用：
    - 用户分享个人信息时（"我叫XX""我在XX工作""我住在XX"）
    - 用户表达偏好时（"我喜欢XX""我爱吃XX"）
    - 用户提到目标时（"我想今年XX""我的目标是XX"）
    - 用户说"记住""记一下"时
    - 任何你觉得值得记住的对话内容

    内容请用完整的自然语言描述，不要简化为关键词。
    例如记录"用户最近开始学吉他，已经报班上课一周了"而不是"吉他"。

    分类说明：personal_info（个人信息）、preference（偏好习惯）、
    goal（目标计划）、note（笔记）、general（其他）。

    Args:
        content: 要记住的完整内容（用自然语言描述，如"用户叫张三，在北京做程序员，喜欢喝美式咖啡"）
        category: 分类：personal_info, preference, goal, note, general（默认 general）
        importance: 重要性 0.0~1.0，越重要的记忆越容易被优先回顾（默认 0.5）

    Returns:
        记忆存储确认
    """
    entry = memory_repo.create_memory(
        MemoryCreate(
            content=content, category=category, importance=importance, source="chat"
        )
    )
    cat_labels = {
        "personal_info": "个人信息",
        "preference": "偏好",
        "goal": "目标",
        "note": "笔记",
        "general": "其他",
    }
    label = cat_labels.get(category, category)
    badge = "⭐" if importance >= 0.8 else "🧠"
    return f"{badge} 已记住（{label}）：「{entry.content[:80]}」"


@tool
def recall_facts_tool(query: str, category: str | None = None) -> str:
    """回忆关于用户的个人信息。Recall personal facts about the user.

    使用语义搜索（而非关键词匹配），可以根据意思找到相关记忆。
    当需要根据用户个人背景提供建议、分析问题或回答个人问题时使用。

    建议：在给出个性化建议前先用此工具了解用户背景。

    Args:
        query: 搜索关键词或句子，如"用户喜欢什么""工作相关""目标计划"
        category: 可选分类过滤：personal_info, preference, goal, note, general

    Returns:
        匹配的记忆列表（按语义相关性排序）
    """
    results = memory_repo.search_similar(query, top_k=5, category=category)
    if not results:
        return f"🔍 没有找到与「{query}」相关的记忆。"

    cat_labels = {
        "personal_info": "个人信息",
        "preference": "偏好",
        "goal": "目标",
        "note": "笔记",
        "general": "其他",
    }
    lines = [f"🔍 找到 {len(results)} 条相关记忆："]
    for i, m in enumerate(results, 1):
        label = cat_labels.get(m.category, m.category)
        star = " ⭐" if m.importance >= 0.8 else ""
        lines.append(f"  {i}. [{label}{star}] {m.content[:100]}")
    return "\n".join(lines)


@tool
def forget_fact_tool(memory_id: int) -> str:
    """删除某条记忆。Delete a memory by its ID.

    当用户要求删除某条记忆时使用。ID 可以从 recall_facts_tool 的结果中看到。

    Args:
        memory_id: 要删除的记忆 ID 编号

    Returns:
        删除确认
    """
    success = memory_repo.delete_memory(memory_id)
    if success:
        return f"🗑️ 已删除记忆 (ID: {memory_id})"
    return f"❌ 没有找到 ID 为 {memory_id} 的记忆。"



@tool
def clear_expired_events_tool() -> str:
    """清除所有已过期的日程事件。Clear all expired schedule events.

    当用户说"清除过期日程""清理过期事件""删除所有过期的日程""清一下日程"
    等表达时使用。会删除所有已经结束的日程。

    Returns:
        清理结果确认字符串
    """
    count = repo.delete_expired_events()
    if count == 0:
        return "📭 没有过期的日程需要清理。"
    return f"🗑️ 已清理 {count} 个过期日程。"



@tool
def web_search_tool(query: str) -> str:
    """搜索互联网获取最新信息。Search the web for current information.

    当用户询问实时信息、最新消息、你不知道的事情，或者需要联网搜索
    才能回答的问题时使用。支持中文和英文搜索。

    用法："查一下今天的新闻""搜索XX事件""帮我了解一下XX"
    会返回搜索结果摘要，并自动抓取第一个结果的详细内容。

    Args:
        query: 搜索关键词或问题

    Returns:
        搜索结果字符串（含标题、摘要、链接和内容摘要）
    """
    return search_web(query, max_results=5, fetch_content=True, max_content_chars=2000)


# ── Reminder Tools ──────────────────────────────────────────────────────


@tool
def create_reminder_tool(
    title: str,
    trigger_time: str,
    description: str = "",
    recurring: str | None = None,
) -> str:
    """创建定时提醒。Create a scheduled reminder.

    当用户说"提醒我XXX""帮我记个提醒""设置提醒""到时间提醒我""闹钟"
    "X小时后提醒我""明天X点提醒我"等表达时使用。
    时间可以用中文，如"5分钟后""明天下午3点""后天早上8点"。

    例如：
    - "提醒我5分钟后喝水" → title="喝水", trigger_time="5分钟后"
    - "每天上午9点提醒我站会" → title="站会", trigger_time="每天上午9点", recurring="0 9 * * *"
    - "明天下午3点提醒我开会" → title="开会", trigger_time="明天下午3点"

    Args:
        title: 提醒标题（必填），如"喝水""开会""吃药"
        trigger_time: 触发时间/间隔（必填），支持中文相对时间如"5分钟后""明天下午3点"，
                      也支持"YYYY-MM-DD HH:MM"格式
        description: 提醒详情文字（可选）
        recurring: 重复规则 cron 表达式（可选），如"0 9 * * *"表示每天早上9点

    Returns:
        创建结果确认字符串
    """
    from app.reminder.models import ReminderCreate
    from app.reminder.repository import ReminderRepository
    from app.reminder.scheduler import schedule_reminder_job

    # Parse the trigger time
    parsed = _parse_time(trigger_time)
    if parsed is None:
        raise ValueError(
            f"无法解析触发时间：{trigger_time}。请提供具体时间，如‘5分钟后’或‘明天下午3点’。"
        )

    data = ReminderCreate(
        title=title,
        description=description,
        trigger_at=parsed,
        recurring=recurring,
    )
    repo = ReminderRepository()
    reminder = repo.create(data)
    schedule_reminder_job(reminder)

    trigger_str = parsed.strftime("%Y-%m-%d %H:%M")
    recurring_str = f" (重复: {recurring})" if recurring else ""
    return (
        f"⏰ 已创建提醒：**{title}**\n"
        f"   📅 触发时间：{trigger_str}{recurring_str}\n"
        f"   🆔 ID: {reminder.id}"
    )


@tool
def list_reminders_tool(status: str | None = None) -> str:
    """查询定时提醒列表。List scheduled reminders.

    当用户问"查看提醒""有什么提醒""我的提醒""查一下提醒"等表达时使用。

    Args:
        status: 筛选状态：pending（待触发）, fired（已触发）, cancelled（已取消）。
                不传则返回所有。

    Returns:
        提醒列表字符串
    """
    from app.reminder.repository import ReminderRepository

    repo = ReminderRepository()
    if status:
        if status == "pending":
            reminders = repo.list_pending()
        elif status == "fired":
            reminders = [r for r in repo.list_all() if r.status == "fired"]
        elif status == "cancelled":
            reminders = [r for r in repo.list_all() if r.status == "cancelled"]
        else:
            return f"❌ 不支持的状态：{status}。可用值：pending, fired, cancelled"
    else:
        reminders = repo.list_all()

    if not reminders:
        return "📭 没有找到提醒。"

    status_labels = {"pending": "⏳待触发", "fired": "✅已触发", "cancelled": "❌已取消"}
    lines = [f"📋 共 {len(reminders)} 条提醒："]
    for i, r in enumerate(reminders, 1):
        label = status_labels.get(r.status, r.status)
        lines.append(
            f"  {i}. {label} **{r.title}**  "
            f"({r.trigger_at.strftime('%Y-%m-%d %H:%M')})  [ID: {r.id}]"
        )
    return "\n".join(lines)


@tool
def delete_reminder_tool(reminder_id: int) -> str:
    """删除定时提醒。Delete a scheduled reminder by its ID.

    当用户说"删除提醒""取消提醒""移除提醒""不提醒了"等表达时使用。
    ID 可以从 list_reminders_tool 的结果中看到。

    Args:
        reminder_id: 提醒 ID (数字)

    Returns:
        删除结果确认字符串
    """
    from app.reminder.repository import ReminderRepository
    from app.reminder.scheduler import cancel_reminder_job

    repo = ReminderRepository()
    # First check it exists and report its title
    reminder = repo.get_by_id(reminder_id)
    if not reminder:
        return f"❌ 未找到 ID 为 {reminder_id} 的提醒。"

    title = reminder.title
    success = repo.delete(reminder_id)
    if success:
        cancel_reminder_job(reminder_id)
        return f"🗑️ 已删除提醒：**{title}** (ID: {reminder_id})"
    return f"❌ 删除提醒失败 (ID: {reminder_id})"


# ── Tool Registry ────────────────────────────────────────────────────

ALL_TOOLS = [
    create_event_tool,
    list_events_tool,
    update_event_tool,
    delete_event_tool,
    clear_expired_events_tool,
    web_search_tool,
    search_events_tool,
    get_current_datetime_tool,
    remember_fact_tool,
    recall_facts_tool,
    forget_fact_tool,
    create_reminder_tool,
    list_reminders_tool,
    delete_reminder_tool,
]

