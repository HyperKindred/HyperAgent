"""LangGraph agent definition using create_react_agent."""

from langchain_openai import ChatOpenAI
from langgraph.graph.message import RemoveMessage
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import get_system_prompt
from app.agent.tools import ALL_TOOLS
from app.config import settings
from app.memory.checkpointer import get_checkpointer


def _make_llm():
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=60,
        max_retries=3,
    )


def build_agent():
    """Build a fresh LangGraph ReAct agent.

    The agent is rebuilt on every call (~100 ms) so the system prompt
    always contains the current time and any pending calendar notifications.
    """
    return create_react_agent(
        model=_make_llm(),
        tools=ALL_TOOLS,
        prompt=get_system_prompt(),  # string — callable 形式有 bug，模型不调用工具
        checkpointer=get_checkpointer(),
    )


def run_agent(user_input: str, thread_id: str = "hyperagent-main") -> str:
    """Synchronously invoke the agent, returning the final assistant message.

    Before each call, automatically trims old messages if the conversation
    exceeds ``max_history_messages``.  This keeps the prompt compact and
    prevents context-window overflow.
    """
    agent = build_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # ── 自动裁剪过长的对话历史 ──────────────────────────────────────
    _trim_if_needed(agent, config)

    response = agent.invoke(
        {"messages": [("user", user_input)]},
        config=config,
    )
    return response["messages"][-1].content


# ── internal helpers ────────────────────────────────────────────────

def _trim_if_needed(agent, config: dict) -> None:
    """If conversation has more than ``max_history_messages``, remove the
    oldest user/assistant/tool messages so the LLM always sees a compact context."""
    max_msgs = settings.max_history_messages
    if max_msgs <= 0:
        return  # 0 or negative means "never trim"

    try:
        snapshot = agent.get_state(config)
    except Exception:
        return

    messages = snapshot.values.get("messages", []) if snapshot.values else []
    if len(messages) <= max_msgs:
        return

    # 计算需要删除的消息数量
    excess = len(messages) - max_msgs
    to_remove = messages[:excess]

    # 用 RemoveMessage 删除旧消息（兼容 add_messages reducer）
    removals = [RemoveMessage(id=m.id) for m in to_remove]
    agent.update_state(config, {"messages": removals})
