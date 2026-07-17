"""Runtime settings, provider safety, and model compatibility tests."""

from __future__ import annotations

import json

import pytest

from app.api import settings as settings_api
from app.api.settings import (
    ProviderRequest,
    SettingsUpdate,
    _key_value,
    _post_stream,
    normalize_base_url,
)
from app.config import Settings
from app.memory.embeddings import EmbeddingConfig, EmbeddingResult
from app.memory.models import Memory, MemoryCreate
from app.memory.repository import MemoryRepository
from app.settings.service import RuntimeSettingsService


class FakeSecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def make_settings(tmp_path, **overrides):
    return Settings(_env_file=None, data_dir=tmp_path, **overrides)


def test_runtime_settings_store_secrets_outside_json(tmp_path):
    secret_store = FakeSecretStore()
    service = RuntimeSettingsService(secret_store)
    current = make_settings(tmp_path)

    service.update(
        current,
        {
            "provider": "my_jarvis",
            "llm_base_url": "https://api.aijws.com/v1",
            "llm_model": "gpt-5.6-terra",
        },
        llm_api_key="sk-test-secret",
    )

    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-test-secret" not in raw
    assert secret_store.values["llm_api_key"] == "sk-test-secret"

    reloaded = make_settings(tmp_path)
    RuntimeSettingsService(secret_store).load_into(reloaded)
    assert reloaded.llm_model == "gpt-5.6-terra"
    assert reloaded.llm_api_key == "sk-test-secret"


def test_runtime_settings_persists_assistant_style_and_public_preferences(tmp_path):
    service = RuntimeSettingsService(FakeSecretStore())
    current = make_settings(tmp_path)

    result = service.update(
        current,
        {
            "assistant_style": "concise",
            "timezone": "Asia/Tokyo",
            "max_history_messages": 80,
            "search_engine_url": "https://search.example",
        },
    )

    assert result["assistant_style"] == "concise"
    assert result["timezone"] == "Asia/Tokyo"
    assert result["max_history_messages"] == 80
    assert result["search_engine_url"] == "https://search.example"

    reloaded = make_settings(tmp_path)
    RuntimeSettingsService(FakeSecretStore()).load_into(reloaded)
    assert reloaded.assistant_style == "concise"


def test_clear_secret_shadows_legacy_env_value(tmp_path):
    secret_store = FakeSecretStore()
    service = RuntimeSettingsService(secret_store)
    current = make_settings(tmp_path, llm_api_key="legacy-key")

    service.update(current, {}, clear_llm_api_key=True)
    assert current.llm_api_key == ""

    reloaded = make_settings(tmp_path, llm_api_key="legacy-key")
    RuntimeSettingsService(secret_store).load_into(reloaded)
    assert reloaded.llm_api_key == ""


def test_settings_json_contains_only_whitelisted_fields(tmp_path):
    service = RuntimeSettingsService(FakeSecretStore())
    current = make_settings(tmp_path)
    service.update(current, {"llm_model": "gpt-5.6-terra"})

    payload = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert set(payload) == {"version", "config", "secret_disabled"}
    assert "llm_api_key" not in payload["config"]
    assert "github_token" not in payload["config"]


def test_integration_credentials_are_kept_outside_runtime_settings_file(tmp_path):
    secret_store = FakeSecretStore()
    service = RuntimeSettingsService(secret_store)
    current = make_settings(tmp_path)

    service.update(
        current,
        {
            "timezone": "Asia/Tokyo",
            "max_history_messages": 60,
            "github_username": "octocat",
            "qq_email_address": "user@qq.com",
        },
        github_token="github-secret",
        notion_token="notion-secret",
        qq_email_auth_code="qq-secret",
        weather_api_key="weather-secret",
    )

    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "github-secret" not in raw
    assert "notion-secret" not in raw
    assert "qq-secret" not in raw
    assert "weather-secret" not in raw
    assert secret_store.values["github_token"] == "github-secret"

    reloaded = make_settings(tmp_path)
    RuntimeSettingsService(secret_store).load_into(reloaded)
    assert reloaded.github_token == "github-secret"
    assert reloaded.notion_token == "notion-secret"
    assert reloaded.qq_email_auth_code == "qq-secret"
    assert reloaded.weather_api_key == "weather-secret"
    assert reloaded.timezone == "Asia/Tokyo"
    assert reloaded.max_history_messages == 60


def test_runtime_settings_rolls_back_all_credentials_when_json_save_fails(
    tmp_path, monkeypatch
):
    secret_store = FakeSecretStore()
    old_values = {
        "llm_api_key": "old-llm",
        "embedding_api_key": "old-embedding",
        "github_token": "old-github",
        "notion_token": "old-notion",
        "qq_email_auth_code": "old-qq",
        "weather_api_key": "old-weather",
    }
    secret_store.values.update(old_values)
    service = RuntimeSettingsService(secret_store)
    current = make_settings(tmp_path, **old_values)

    def fail_write(_settings):
        raise OSError("disk full")

    monkeypatch.setattr(service, "_write", fail_write)
    with pytest.raises(OSError, match="disk full"):
        service.update(
            current,
            {"timezone": "Asia/Tokyo"},
            llm_api_key="new-llm",
            embedding_api_key="new-embedding",
            github_token="new-github",
            notion_token="new-notion",
            qq_email_auth_code="new-qq",
            weather_api_key="new-weather",
        )

    assert secret_store.values == old_values
    assert current.timezone == "Asia/Shanghai"
    for name, value in old_values.items():
        assert getattr(current, name) == value


def test_my_jarvis_preset_migrates_legacy_endpoint_and_model(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "version": 1,
                "config": {
                    "provider": "my_jarvis",
                    "llm_base_url": "https://api.myjarvis.ai/v1",
                    "llm_model": "deepseek-v4-flash",
                },
                "secret_disabled": {},
            }
        ),
        encoding="utf-8",
    )
    current = make_settings(tmp_path)
    RuntimeSettingsService(FakeSecretStore()).load_into(current)

    assert current.llm_model == "gpt-5.6-terra"
    assert current.llm_base_url == "https://api.aijws.com/v1"
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["config"]["llm_model"] == "gpt-5.6-terra"
    assert saved["config"]["llm_base_url"] == "https://api.aijws.com/v1"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.aijws.com/v1/",
        "http://localhost:8000/v1",
        "http://127.0.0.1:8000/v1",
    ],
)
def test_base_url_validation_accepts_https_and_loopback(url):
    assert normalize_base_url(url).endswith("v1")


@pytest.mark.parametrize(
    "url",
    ["http://example.com/v1", "ftp://example.com", "https://user:pass@example.com"],
)
def test_base_url_validation_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        normalize_base_url(url)


def test_timezone_validation_rejects_unknown_zone():
    with pytest.raises(ValueError, match="时区无效"):
        SettingsUpdate(timezone="Mars/Olympus")


def test_stored_key_is_not_reused_for_a_different_base_url():
    with pytest.raises(Exception) as exc_info:
        _key_value(None, "stored-secret", "https://evil.example/v1", "https://api.aijws.com/v1")
    assert "地址已改变" in str(exc_info.value.detail)


def test_model_discovery_returns_sorted_ids_without_exposing_key(monkeypatch):
    class Response:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"id": "gpt-5.6-terra"}, {"id": "gpt-5.6-sol"}]}

    monkeypatch.setattr(settings_api.settings, "llm_api_key", "stored-secret")
    monkeypatch.setattr(settings_api.settings, "llm_base_url", "https://api.aijws.com/v1")
    monkeypatch.setattr(settings_api.requests, "get", lambda *_args, **_kwargs: Response())
    result = settings_api.discover_models(
        ProviderRequest(base_url="https://api.aijws.com/v1")
    )
    assert result == {"models": ["gpt-5.6-sol", "gpt-5.6-terra"]}
    assert "secret" not in json.dumps(result)


def test_stream_capability_probe_accepts_sse(monkeypatch):
    class Response:
        ok = True
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def iter_lines(decode_unicode=True):
            assert decode_unicode is True
            return iter(['data: {"choices":[{"delta":{"content":"OK"}}]}'])

    monkeypatch.setattr(settings_api.requests, "post", lambda *_args, **_kwargs: Response())
    _post_stream("https://api.example/v1/chat/completions", "test-key", {"model": "test"})


def test_gpt56_client_omits_temperature_and_sets_tool_compatible_reasoning(monkeypatch):
    from app.agent import graph

    captured = {}
    monkeypatch.setattr(graph, "ChatOpenAI", lambda **kwargs: captured.update(kwargs) or kwargs)
    monkeypatch.setattr(graph.settings, "llm_model", "gpt-5.6-terra")
    monkeypatch.setattr(graph.settings, "llm_temperature", None)
    monkeypatch.setattr(graph.settings, "llm_reasoning_effort", "none")

    graph._make_llm()
    assert captured["model"] == "gpt-5.6-terra"
    assert captured["reasoning_effort"] == "none"
    assert "temperature" not in captured


def test_settings_change_refreshes_recurring_jobs_and_embedding_index(monkeypatch):
    from app.agent import graph
    from app.memory import embeddings, reindex
    from app.reminder import scheduler

    monkeypatch.setattr(settings_api.settings, "timezone", "Asia/Shanghai")
    monkeypatch.setattr(settings_api.settings, "embedding_mode", "separate")
    monkeypatch.setattr(settings_api.settings, "embedding_model", "old-model")
    monkeypatch.setattr(graph, "reset_llm_cache", lambda: None)
    monkeypatch.setattr(embeddings, "reset_embedding_probe", lambda: None)

    calls = {"reminders": 0, "reindex": []}
    monkeypatch.setattr(
        scheduler,
        "reschedule_recurring_jobs",
        lambda: calls.__setitem__("reminders", calls["reminders"] + 1),
    )

    class FakeReindexManager:
        def start(self, *, restart_if_running=False):
            calls["reindex"].append(restart_if_running)
            return self.status()

        @staticmethod
        def status():
            return {
                "state": "running",
                "total": 0,
                "indexed": 0,
                "failed": 0,
                "fingerprint": None,
            }

    monkeypatch.setattr(reindex, "reindex_manager", FakeReindexManager())

    def fake_update(current, values, **_kwargs):
        for name, value in values.items():
            setattr(current, name, value)
        return {"timezone": current.timezone}

    monkeypatch.setattr(settings_api.runtime_settings, "update", fake_update)
    result = settings_api.update_settings(
        SettingsUpdate(timezone="Asia/Tokyo", embedding_model="new-model")
    )

    assert calls == {"reminders": 1, "reindex": [True]}
    assert result["reindex"]["state"] == "running"


def test_embedding_auto_mode_falls_back_to_separate_provider(monkeypatch):
    from app.memory import embeddings

    monkeypatch.setattr(embeddings.settings, "embedding_mode", "auto")
    monkeypatch.setattr(embeddings.settings, "llm_api_key", "chat-key")
    monkeypatch.setattr(embeddings.settings, "llm_base_url", "https://chat.example/v1")
    monkeypatch.setattr(embeddings.settings, "embedding_auto_model", "text-embedding-3-small")
    monkeypatch.setattr(embeddings.settings, "embedding_api_key", "embed-key")
    monkeypatch.setattr(embeddings.settings, "embedding_base_url", "https://embed.example/v1")
    monkeypatch.setattr(embeddings.settings, "embedding_model", "qwen/test")
    embeddings.reset_embedding_probe()

    def fake_request(config: EmbeddingConfig, *_args, **_kwargs):
        return None if config.source == "chat_provider" else [0.1, 0.2, 0.3]

    monkeypatch.setattr(embeddings, "_request_embedding", fake_request)
    result = embeddings.get_embedding_result("hello")
    assert result is not None
    assert result.source == "separate"
    assert result.dimensions == 3


def test_memory_search_ignores_incompatible_embedding(session, monkeypatch):
    memory = Memory(
        content="用户喜欢咖啡",
        category="preference",
        embedding="[0.1, 0.2]",
        embedding_fingerprint="old-provider",
        embedding_model="old-model",
        embedding_dimensions=2,
    )
    session.add(memory)
    session.commit()
    result = EmbeddingResult(
        vector=[0.2, 0.3, 0.4],
        model="new-model",
        dimensions=3,
        fingerprint="new-provider",
        source="separate",
    )
    monkeypatch.setattr("app.memory.repository.get_embedding_result", lambda _text: result)

    found = MemoryRepository(session=session).search_similar("咖啡")
    assert [item.content for item in found] == ["用户喜欢咖啡"]
