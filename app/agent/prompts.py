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
{now.strftime('%Y年%m月%d日 %A %H:%M')}
时区：{settings.timezone}
{notif_block}
【核心规则：日程查询必须使用工具】
当用户询问与日程、安排、计划相关的任何问题时，你**必须**调用
list_events_tool 或 search_events_tool 获取真实数据后再回答。
**不要**凭记忆编造日程内容，**不要**只回复问候语而不查询。

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
