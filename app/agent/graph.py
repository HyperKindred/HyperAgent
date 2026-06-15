"""LangGraph agent definition using create_react_agent."""

import base64
import json
import logging
from typing import Any, AsyncGenerator
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph.message import RemoveMessage
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import get_system_prompt
from app.agent.tools import ALL_TOOLS
from app.config import settings
from app.file_parser.parser import parse_file, MAX_FILE_CHARS
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


def run_agent(
    user_input: str,
    thread_id: str = "hyperagent-main",
    model: str | None = None,
    images: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> str:
    """Synchronously invoke the agent, returning the final assistant message.

    Before each call, automatically trims old messages if the conversation
    exceeds `max_history_messages`.  This keeps the prompt compact and
    prevents context-window overflow.
    """
    # ── 有图时自动切换到视觉模型 ────────────────────────────────────
    has_images = images and len(images) > 0
    effective_model = settings.vision_model if (has_images and settings.vision_model) else model

    agent = build_agent(model=effective_model)
    config = {"configurable": {"thread_id": thread_id}}

    _trim_if_needed(agent, config)
    _sanitize_history_for_model(agent, config, effective_model)

    # ── 构建消息 ─────────────────────────────────────────────────────
    # 策略：
    #   有图片 → HumanMessage(content=[text, image_url_1, ...])
    #   有文件 → 解析文件文本，注入到用户消息正文前
    #   两者都有 → 文件文本 + 用户输入作为 text，图片作为 image_url
    #   两者都无 → 纯文本消息
    has_files = files and len(files) > 0

    if has_images:
        # 构造文本部分（可能包含文件内容）
        text_parts = [user_input]
        if has_files:
            text_parts.insert(0, f"用户上传了以下文件，内容如下：\n{_parse_uploaded_files(files)}")  # type: ignore[arg-type]
        content: list[dict] = [{"type": "text", "text": "\n\n".join(text_parts)}]
        for img_b64 in images:
            img_url = _clean_image_url(img_b64)
            content.append({
                "type": "image_url",
                "image_url": {"url": img_url}
            })
        messages = [HumanMessage(content=content)]
    elif has_files:
        file_context = _parse_uploaded_files(files)  # type: ignore[arg-type]
        augmented_input = f"用户上传了以下文件，内容如下：\n{file_context}\n\n---\n\n{user_input}"
        messages = [("user", augmented_input)]
    else:
        messages = [("user", user_input)]

    response = agent.invoke(
        {"messages": messages},
        config=config,
    )
    return response["messages"][-1].content


async def stream_agent(
    user_input: str,
    thread_id: str = "hyperagent-main",
    model: str | None = None,
    images: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream the agent's response token-by-token via Server-Sent Events.

    Uses `agent.astream_events()` with `version="v2"` and filters for
    `on_chat_model_stream` events to get per-token output from the LLM.

    Yields ``data: {"type": "token", "content": "..."}\n\n`` per token
    and ``data: {"type": "done"}\n\n`` when finished.
    """
    try:
        # ── 有图时自动切换到视觉模型 ──────────────────────────────────
        has_images = images and len(images) > 0
        effective_model = settings.vision_model if (has_images and settings.vision_model) else model

        agent = build_agent(model=effective_model)
        config = {"configurable": {"thread_id": thread_id}}
        _trim_if_needed(agent, config)
        _sanitize_history_for_model(agent, config, effective_model)

        # ── 构建消息 ─────────────────────────────────────────────────
        has_files = files and len(files) > 0

        if has_images:
            # 文本部分（可能包含文件内容）
            text_parts = [user_input]
            if has_files:
                text_parts.insert(0, f"用户上传了以下文件，内容如下：\n{_parse_uploaded_files(files)}")  # type: ignore[arg-type]
            content = [{"type": "text", "text": "\n\n".join(text_parts)}]
            for img_b64 in images:
                img_url = _clean_image_url(img_b64)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })
            input_messages = [HumanMessage(content=content)]
        elif has_files:
            file_context = _parse_uploaded_files(files)  # type: ignore[arg-type]
            augmented_input = f"用户上传了以下文件，内容如下：\n{file_context}\n\n---\n\n{user_input}"
            input_messages = [("user", augmented_input)]
        else:
            input_messages = [("user", user_input)]

        async for event in agent.astream_events(
            {"messages": input_messages},
            config,
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        error_msg = str(e)
        logger.exception("stream_agent failed: %s", error_msg)
        # Truncate very long error messages (e.g. full API responses)
        if len(error_msg) > 300:
            error_msg = error_msg[:300] + "..."
        yield f"data: {json.dumps({'type': 'error', 'content': f'请求失败: {error_msg}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ── internal helpers ────────────────────────────────────────────────

_MAX_FILE_CHARS = MAX_FILE_CHARS  # re-export for consistency


def _clean_image_url(raw: str) -> str:
    """Normalize a user-supplied image to a valid data URL.

    Handles three cases:
    1. Plain base64 string  →  ``data:image/jpeg;base64,<raw>``
    2. Proper data URL      →  used as-is
    3. Double-encoded URL   →  strips inner ``data:image/...;base64,``
       (known Electron / clipboard quirk)
    """
    # Case 3: the base64 portion itself starts with a data-URL — strip
    # e.g. "data:image/png;base64,data:image/png;base64,ABC..."
    if ";base64," in raw:
        prefix, _, rest = raw.partition(";base64,")
        while rest.startswith("data:"):
            if ";base64," in rest:
                _, _, rest = rest.partition(";base64,")
            else:
                break
        return prefix + ";base64," + rest
    # Case 2: already a proper data URL
    if raw.startswith("data:image/"):
        return raw
    # Case 1: plain base64
    return f"data:image/jpeg;base64,{raw}"


def _sanitize_history_for_model(agent, config: dict, model: str | None) -> None:
    """Remove old HumanMessages with ``image_url`` content from history.

    The vision model stores messages with ``image_url`` blocks in the history.
    When the next turn uses a plain-text model, those blocks cause a 400 error.
    This function removes those messages entirely to avoid the issue.
    """
    is_vision = model and "vision" in model.lower()
    if is_vision:
        return
    try:
        snapshot = agent.get_state(config)
    except Exception:
        return
    messages = snapshot.values.get("messages", []) if snapshot.values else []
    if not messages:
        return

    # Remove HumanMessages that contain image_url content
    ids_to_remove = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list) and any(
            isinstance(c, dict) and c.get("type") == "image_url" for c in content
        ):
            ids_to_remove.append(msg.id)

    if not ids_to_remove:
        return

    from langgraph.graph.message import RemoveMessage

    removals = [RemoveMessage(id=mid) for mid in ids_to_remove]
    try:
        agent.update_state(config, {"messages": removals})
    except Exception:
        pass


def _parse_uploaded_files(files: list[dict[str, Any]]) -> str:
    """Decode and parse uploaded files, returning a formatted text block.

    Each file dict must have ``name``, ``content`` (base64), and
    optionally ``mime`` keys.
    """
    blocks: list[str] = []
    for f in files:
        # Handle both dicts and Pydantic model objects
        name = f.get("name") if isinstance(f, dict) else getattr(f, "name", "unknown")
        raw_b64 = f.get("content") if isinstance(f, dict) else getattr(f, "content", "")
        mime = f.get("mime", "") if isinstance(f, dict) else getattr(f, "mime", "")
        if not raw_b64:
            blocks.append(f"--- {name} ---\n[空文件]")
            continue
        try:
            raw_bytes = base64.b64decode(raw_b64)
        except Exception:
            blocks.append(f"--- {name} ---\n[文件解码失败]")
            continue
        try:
            text = parse_file(raw_bytes, name, mime)
            blocks.append(f"--- {name} ---\n{text}")
        except ValueError as exc:
            blocks.append(f"--- {name} ---\n[{exc}]")
    return "\n\n".join(blocks)


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

    excess = len(messages) - max_msgs
    # Collect tool_call IDs from messages we are about to remove.
    removed_tc_ids: set[str] = set()
    for msg in messages[:excess]:
        tcs = getattr(msg, "tool_calls", None)
        if tcs:
            for tc in tcs:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    removed_tc_ids.add(tc_id)

    to_remove = messages[:excess]
    # Extend removal: also remove tool responses whose parent AI message
    # with tool_calls was just removed (prevents orphaned tool messages).
    for msg in messages[excess:]:
        if getattr(msg, "type", "") == "tool":
            tc_id = getattr(msg, "tool_call_id", None)
            if tc_id and tc_id in removed_tc_ids:
                to_remove.append(msg)

    removals = [RemoveMessage(id=m.id) for m in to_remove]
    agent.update_state(config, {"messages": removals})

