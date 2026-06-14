"""LangGraph agent definition using create_react_agent."""

import json
import logging
from typing import AsyncGenerator
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI
from langgraph.graph.message import RemoveMessage
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import get_system_prompt
from app.agent.tools import ALL_TOOLS
from app.config import settings
from app.memory.checkpointer import get_checkpointer


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite import SqliteSaver


# ── cached singletons ──────────────────────────────────────────────
# The LLM client and checkpointer are reused across agent rebuilds so
# we don't open a new connection / create a new client every turn.

_llm: ChatOpenAI | None = None
_checkpointer: "SqliteSaver | None" = None


def _get_llm(model: str | None = None) -> ChatOpenAI:
    global _llm
    if model is not None:
        return _make_llm(model)
    if _llm is None:
        _llm = _make_llm()
    return _llm


def _get_checkpointer() -> "SqliteSaver":
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = get_checkpointer()
    return _checkpointer


def _make_llm(model: str | None = None):
    return ChatOpenAI(
        model=model or settings.llm_model or settings.deepseek_model,
        api_key=settings.llm_api_key or settings.deepseek_api_key,
        base_url=settings.llm_base_url or settings.deepseek_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        streaming=True,
        timeout=60,
        max_retries=3,
    )


def build_agent(model: str | None = None):
    """Build a fresh LangGraph ReAct agent.

    The agent itself is rebuilt every turn so the system prompt always
    contains the current time / memory context / notifications, but the
    underlying LLM client and checkpointer are cached.
    """
    return create_react_agent(
        model=_get_llm(model),
        tools=ALL_TOOLS,
        prompt=get_system_prompt(),  # string — callable 形式有 bug，模型不调用工具
        checkpointer=_get_checkpointer(),
    )


def run_agent(user_input: str, thread_id: str = "hyperagent-main", model: str | None = None) -> str:
    """Synchronously invoke the agent, returning the final assistant message.

    Before each call, automatically trims old messages if the conversation
    exceeds `max_history_messages`.  This keeps the prompt compact and
    prevents context-window overflow.
    """
    agent = build_agent(model=model)
    config = {"configurable": {"thread_id": thread_id}}

    # ── 自动裁剪过长的对话历史 ──────────────────────────────────────
    _trim_if_needed(agent, config)

    response = agent.invoke(
        {"messages": [("user", user_input)]},
        config=config,
    )
    return response["messages"][-1].content


async def stream_agent(
    user_input: str,
    thread_id: str = "hyperagent-main",
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream the agent's response token-by-token via Server-Sent Events.

    Uses `agent.astream_events()` with `version="v2"` and filters for
    `on_chat_model_stream` events to get per-token output from the LLM.

    Yields `data: {"type": "token", "content": "..."}\n\n` per token
    and `data: {"type": "done"}\n\n` when finished.
    """
    try:
        agent = build_agent(model=model)
        config = {"configurable": {"thread_id": thread_id}}
        _trim_if_needed(agent, config)

        async for event in agent.astream_events(
            {"messages": [("user", user_input)]},
            config,
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception:
        logger.exception("stream_agent failed")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Agent error'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ── internal helpers ────────────────────────────────────────────────

def _trim_if_needed(agent, config: dict) -> None:
    """If conversation has more than `max_history_messages`, remove the
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

