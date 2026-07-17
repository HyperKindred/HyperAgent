"""Chat request validation and safe provider error behavior."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agent.graph import _public_model_error
from app.api.chat import ChatRequest, _require_llm_configuration


def test_chat_request_limits_attachment_counts():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", images=["one", "two", "three", "four"])
    with pytest.raises(ValidationError):
        ChatRequest(
            message="hello",
            files=[{"name": f"{index}.txt", "content": "YQ=="} for index in range(6)],
        )


def test_chat_request_limits_each_image_payload_size():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", images=["x" * 7_000_001])


def test_chat_request_supports_attachment_only_but_rejects_empty():
    request = ChatRequest(message="", images=["data:image/jpeg;base64,YQ=="])
    assert request.message == ""
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


def test_model_error_does_not_return_provider_secret():
    message = _public_model_error(RuntimeError("401 invalid key sk-secret-value"))
    assert "sk-secret" not in message
    assert "API Key" in message


def test_missing_model_configuration_returns_setup_action(monkeypatch):
    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api.settings, "llm_api_key", "")
    with pytest.raises(HTTPException) as exc_info:
        _require_llm_configuration()
    assert exc_info.value.status_code == 409
    assert "设置" in exc_info.value.detail
