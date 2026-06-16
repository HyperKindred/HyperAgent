"""Thread management REST endpoints."""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.thread.models import ThreadCreate, ThreadResponse, ThreadUpdate
from app.thread.repository import ThreadRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["thread"])


class NewThreadRequest(BaseModel):
    title: str = "新对话"


class RenameRequest(BaseModel):
    title: str


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
    from app.memory.checkpointer import get_checkpointer

    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = checkpointer.get_tuple(config)
    except Exception:
        state = None

    if state is None:
        # Thread exists in metadata but has no checkpoints yet
        return {"thread_id": thread_id, "messages": []}

    messages = []
    for msg in getattr(state.checkpoint, "messages", []):
        role = getattr(msg, "type", "")
        if role in ("human", "ai"):
            content = getattr(msg, "content", "")
            messages.append({"role": role, "content": content})

    return {"thread_id": thread_id, "messages": messages}


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
