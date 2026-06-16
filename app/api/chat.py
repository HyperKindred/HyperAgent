"""Chat REST endpoints."""

import uuid
import json

from pydantic import BaseModel
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.graph import run_agent, stream_agent

router = APIRouter()


class FileItem(BaseModel):
    """An uploaded file attached to a chat message."""

    name: str  # filename including extension, e.g. "report.pdf"
    content: str  # base64-encoded file content
    mime: str = ""  # MIME type, e.g. "application/pdf"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "hyperagent-main"
    model: str | None = None
    images: list[str] = []
    files: list[FileItem] = []


class ChatResponse(BaseModel):
    reply: str


class ThreadResponse(BaseModel):
    thread_id: str


@router.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to a specific agent thread and get a reply."""
    reply = run_agent(
        request.message,
        thread_id=request.thread_id,
        model=request.model,
        images=request.images or None,
        files=[f.model_dump() for f in request.files] if request.files else None,
    )
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and receive a streaming SSE response.

    The response is a Server-Sent Events stream where each ``data``
    line carries a JSON object.  Event types:
    - ``{"type": "token", "content": "..."}`` — one token of the reply
    - ``{"type": "done"}`` — the agent has finished
    """
    return StreamingResponse(
        stream_agent(request.message, thread_id=request.thread_id, model=request.model, images=request.images or None, files=[f.model_dump() for f in request.files] if request.files else None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/threads")
def new_thread() -> ThreadResponse:
    """Create a new conversation thread and return its ID."""
    from app.thread.models import ThreadCreate
    from app.thread.repository import ThreadRepository

    thread_id = f"hyperagent-{uuid.uuid4().hex[:8]}"
    repo = ThreadRepository()
    repo.create(ThreadCreate(thread_id=thread_id))
    return ThreadResponse(thread_id=thread_id)


