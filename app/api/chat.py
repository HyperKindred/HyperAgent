"""Chat REST endpoints."""

from pydantic import BaseModel
from fastapi import APIRouter

from app.agent.graph import run_agent

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the AI agent and get a reply."""
    reply = run_agent(request.message)
    return ChatResponse(reply=reply)
