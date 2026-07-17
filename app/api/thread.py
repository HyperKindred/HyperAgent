"""Thread management REST endpoints."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.thread.models import ThreadCreate, ThreadResponse
from app.thread.repository import ThreadRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["thread"])


class NewThreadRequest(BaseModel):
    title: str = "新对话"


class RenameRequest(BaseModel):
    title: str


def _visible_messages(checkpoint: dict) -> list[dict[str, str]]:
    """Extract displayable messages from LangGraph's checkpoint payload."""
    values = checkpoint.get("channel_values", {})
    raw_messages = values.get("messages", []) if isinstance(values, dict) else []
    messages: list[dict[str, str]] = []
    for msg in raw_messages:
        role = getattr(msg, "type", "")
        if role not in ("human", "ai"):
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "image_url":
                    parts.append("[图片]")
            content = "\n".join(parts)
        if not isinstance(content, str):
            content = str(content)
        messages.append({"role": "user" if role == "human" else "assistant", "content": content})
    return messages


def _thread_messages(thread_id: str) -> list[dict[str, str]]:
    """Read displayable messages from the latest checkpoint for a thread."""
    from app.memory.checkpointer import get_checkpointer

    checkpointer = None
    try:
        checkpointer = get_checkpointer()
        state = checkpointer.get_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        return _visible_messages(state.checkpoint) if state is not None else []
    except Exception as exc:
        logger.warning("Failed to read thread history for %s: %s", thread_id, exc)
        return []
    finally:
        # This endpoint creates a short-lived saver rather than using the
        # agent's cached checkpointer, so it owns and must close its SQLite
        # connection after the snapshot has been read.
        conn = getattr(checkpointer, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:
                logger.warning("Failed to close thread history connection: %s", exc)


@router.get("/threads", response_model=list[ThreadResponse])
def list_threads():
    """List all conversation threads, newest updated first."""
    repo = ThreadRepository()
    threads = repo.get_all()
    return threads


@router.post("/threads", response_model=ThreadResponse, status_code=201)
def create_thread(data: NewThreadRequest = NewThreadRequest()):
    """Create a new conversation thread."""
    thread_id = f"hyperagent-{uuid.uuid4().hex[:8]}"
    repo = ThreadRepository()
    thread = repo.create(ThreadCreate(thread_id=thread_id, title=data.title))
    logger.info("Thread created via API: %s", thread_id)
    return thread


@router.get("/threads/{thread_id}/messages")
def get_thread_messages(thread_id: str):
    """Get the message history for a thread from checkpoints.

    Returns a list of {role, content} dicts extracted from the latest
    checkpoint snapshot.  Only ``human`` and ``ai`` messages are returned;
    tool-call internals are omitted.
    """
    return {"thread_id": thread_id, "messages": _thread_messages(thread_id)}


@router.get("/threads/{thread_id}/export")
def export_thread(thread_id: str):
    """Export a portable transcript without tool internals or credentials."""
    thread = ThreadRepository().get_by_id(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "format": "hyperagent-thread-backup",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "thread": ThreadResponse.model_validate(thread).model_dump(mode="json"),
        "messages": _thread_messages(thread_id),
    }


@router.put("/threads/{thread_id}")
def rename_thread(thread_id: str, body: RenameRequest):
    """Rename a conversation thread."""
    repo = ThreadRepository()
    thread = repo.update_title(thread_id, body.title)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    logger.info("Thread renamed: %s → %s", thread_id, body.title)
    return {"status": "ok", "id": thread_id, "title": body.title}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    """Delete a thread and its checkpoints."""
    repo = ThreadRepository()
    success = repo.delete(thread_id)
    if not success:
        raise HTTPException(status_code=404, detail="Thread not found")
    logger.info("Thread deleted via API: %s", thread_id)
    return {"status": "ok", "id": thread_id}
