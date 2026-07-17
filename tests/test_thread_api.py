"""Thread history extraction tests for the LangGraph checkpoint format."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from datetime import datetime
from types import SimpleNamespace

from app.api import thread as thread_api
from app.api.thread import _visible_messages
from app.thread.models import Thread


def test_visible_messages_reads_langgraph_channel_values():
    checkpoint = {
        "channel_values": {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="你好，有什么可以帮你？"),
                ToolMessage(content="ignored", tool_call_id="call-1"),
            ]
        }
    }
    assert _visible_messages(checkpoint) == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你？"},
    ]


def test_visible_messages_replaces_image_payload_with_placeholder():
    checkpoint = {
        "channel_values": {
            "messages": [
                HumanMessage(
                    content=[
                        {"type": "text", "text": "分析这张图"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ]
                )
            ]
        }
    }
    assert _visible_messages(checkpoint) == [
        {"role": "user", "content": "分析这张图\n[图片]"}
    ]


def test_thread_history_closes_its_temporary_checkpoint_connection(monkeypatch):
    class FakeConnection:
        closed = False

        def close(self):
            self.closed = True

    class FakeCheckpointer:
        def __init__(self):
            self.conn = FakeConnection()

        def get_tuple(self, _config):
            return SimpleNamespace(
                checkpoint={"channel_values": {"messages": [HumanMessage(content="历史消息")]}}
            )

    checkpointer = FakeCheckpointer()
    import app.memory.checkpointer as checkpointer_module

    monkeypatch.setattr(checkpointer_module, "get_checkpointer", lambda: checkpointer)

    assert thread_api._thread_messages("hyperagent-history") == [
        {"role": "user", "content": "历史消息"}
    ]
    assert checkpointer.conn.closed is True


def test_export_thread_contains_only_portable_thread_data(monkeypatch):
    thread = Thread(
        id="hyperagent-export",
        title="测试对话",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
        message_count=2,
        model="gpt-5.6-terra",
    )

    class FakeRepository:
        def get_by_id(self, _thread_id):
            return thread

    monkeypatch.setattr(thread_api, "ThreadRepository", FakeRepository)
    monkeypatch.setattr(
        thread_api,
        "_thread_messages",
        lambda _thread_id: [{"role": "user", "content": "你好"}],
    )
    payload = thread_api.export_thread("hyperagent-export")

    assert payload["format"] == "hyperagent-thread-backup"
    assert payload["thread"]["title"] == "测试对话"
    assert payload["messages"] == [{"role": "user", "content": "你好"}]
    assert "api_key" not in str(payload).lower()
