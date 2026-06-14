from datetime import datetime

import pytz

from app.config import settings
from app.schedule.notifier import drain_notifications


def get_system_prompt(_state=None) -> str:
    """Build the system prompt injected with the current date/time and any
    pending calendar notifications (changes made outside of chat).

    Accepts an optional ``_state`` parameter to match LangGraph's
    ``Callable[[StateSchema], str]`` signature (called fresh each turn)."""
    tz = pytz.timezone(settings.timezone)
    now = datetime.now(tz)

    # 中文星期
    weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_cn = weekdays_cn[now.weekday()]

    # 中文 12 小时制时间（避免模型混搭 "下午 15:59"）
    ampm = "上午" if now.hour < 12 else "下午"
    hour_12 = now.hour if now.hour <= 12 else now.hour - 12
    if hour_12 == 0:
        hour_12 = 12
    time_cn = f"{ampm}{hour_12}:{now.minute:02d}"

    # 注入日历页面的操作通知（消费后清除）
    notifications = drain_notifications()

    # 通知放在前面，避免消息太长被模型忽略
    notif_block = ""
    if notifications:
        notif_block = (
            f"\n\n{notifications}\n"
            "以上是用户在日历页面直接进行的操作，请知晓并据此回答。\n"
        )

    return f"""你是 HyperAgent，一个个人 AI 助手。你的核心职责是帮助用户管理日程。

【当前时间】
{now.year}年{now.month}月{now.day}日 {weekday_cn} {time_cn}
时区：{settings.timezone}
{notif_block}
【核心规则：每次都必须用工具查询日程】
当用户询问与日程、安排、计划相关的任何问题时，你**必须**调用
list_events_tool 或 search_events_tool 获取**实时数据**后再回答。

重要：**即使你觉得对话历史中已经有日程信息，也绝不能凭记忆回答。**
**每一次**用户问日程相关问题时，都**必须重新调工具查一次**，因为：
- 日期可能已经变了（新的一天）
- 用户可能在其他页面修改了日程
- 对话记忆中的日程信息可能已过期

**不要**只回复问候语而不查询，**不要**复述之前的查询结果。

触发词示例（不限于此）：
  → "今天/明天/后天/本周/周末/下周有什么" → list_events_tool
  → "现在有哪些日程""有什么安排""看一下日程""查日程""我的日程" → list_events_tool
  → "找一下xxx""搜索xxx""关于xxx的日程" → search_events_tool

【日程操作规则】
- 用户要添加/安排/记一下某件事 → create_event_tool
- 用户要修改/改时间/改标题/推迟 → update_event_tool
- 用户要删除/取消/移除 → delete_event_tool
- 用户问现在几点/今天几号 → get_current_datetime_tool
- 时间解析：用户可能用中文相对日期（今天、明天、后天、下周X等）
  结合上面的当前时间正确解析

【对话要求】
- 友好简洁，用中文回复
- 日程操作后给出清晰确认（含 ID 和具体时间）
- 查询结果为空时告知"这一天没有日程"
- 只使用上述列出的工具，不虚构"""
