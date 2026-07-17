"""Cancellation and error-boundary tests for streamed agent responses."""

import asyncio
import json

import pytest

from app.agent import graph


def test_stream_agent_propagates_client_cancellation(monkeypatch):
    class CancelledAgent:
        async def astream_events(self, *_args, **_kwargs):
            raise asyncio.CancelledError()
            yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(graph, "build_agent", lambda **_kwargs: CancelledAgent())

    async def consume_first_event():
        stream = graph.stream_agent("停止测试")
        return await anext(stream)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(consume_first_event())


def test_stream_agent_masks_provider_error(monkeypatch):
    class FailingAgent:
        async def astream_events(self, *_args, **_kwargs):
            raise RuntimeError("401 invalid key sk-provider-secret")
            yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(graph, "build_agent", lambda **_kwargs: FailingAgent())

    async def consume_first_event():
        stream = graph.stream_agent("失败测试")
        return await anext(stream)

    event = asyncio.run(consume_first_event())
    payload = json.loads(event.removeprefix("data: "))
    assert "鉴权失败" in payload["content"]
    assert "sk-provider-secret" not in payload["content"]
