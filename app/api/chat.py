"""Chat REST endpoints."""

import logging
from typing import Annotated

from pydantic import BaseModel, Field, model_validator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.graph import run_agent, stream_agent
from app.thread.repository import ThreadRepository
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class FileItem(BaseModel):
    """An uploaded file attached to a chat message."""

    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=7_000_000)
    mime: str = Field(default="", max_length=120)


ImageItem = Annotated[str, Field(min_length=1, max_length=7_000_000)]


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=30_000)
    thread_id: str = Field(default="hyperagent-main", min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=160)
    images: list[ImageItem] = Field(default_factory=list, max_length=3)
    files: list[FileItem] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.images and not self.files:
            raise ValueError("消息、图片或文件至少需要提供一项")
        return self


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to a specific agent thread and get a reply."""
    _require_llm_configuration()
    _ensure_thread(request.thread_id)
    try:
        reply = run_agent(
            request.message,
            thread_id=request.thread_id,
            model=request.model,
            images=request.images or None,
            files=[f.model_dump() for f in request.files] if request.files else None,
        )
    except Exception as exc:
        logger.exception("Non-streaming chat request failed")
        raise HTTPException(
            status_code=502,
            detail="模型请求失败，请在设置中测试连接后重试。",
        ) from exc
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and receive a streaming SSE response.

    The response is a Server-Sent Events stream where each ``data``
    line carries a JSON object.  Event types:
    - ``{"type": "token", "content": "..."}`` — one token of the reply
    - ``{"type": "done"}`` — the agent has finished
    """
    _require_llm_configuration()
    _ensure_thread(request.thread_id)
    return StreamingResponse(
        stream_agent(request.message, thread_id=request.thread_id, model=request.model, images=request.images or None, files=[f.model_dump() for f in request.files] if request.files else None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _ensure_thread(thread_id: str) -> None:
    """Bump the thread timestamp after a message is sent.

    Only updates metadata that was explicitly created via ``POST /threads``;
    does NOT auto-create metadata for ad-hoc thread IDs like ``hyperagent-main``.
    """
    repo = ThreadRepository()
    repo.touch(thread_id)


def _require_llm_configuration() -> None:
    if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
        raise HTTPException(
            status_code=409,
            detail="请先在设置中配置并保存模型服务。",
        )
