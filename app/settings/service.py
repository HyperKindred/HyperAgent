"""Persist runtime settings without writing API keys to disk."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any

from app.settings.secrets import SecretStore, create_secret_store

logger = logging.getLogger(__name__)

SETTINGS_VERSION = 1
LLM_SECRET = "llm_api_key"
EMBEDDING_SECRET = "embedding_api_key"
GITHUB_SECRET = "github_token"
NOTION_SECRET = "notion_token"
QQ_EMAIL_SECRET = "qq_email_auth_code"
WEATHER_SECRET = "weather_api_key"

SECRET_FIELDS = (
    LLM_SECRET,
    EMBEDDING_SECRET,
    GITHUB_SECRET,
    NOTION_SECRET,
    QQ_EMAIL_SECRET,
    WEATHER_SECRET,
)

PERSISTED_FIELDS = {
    "provider",
    "llm_base_url",
    "llm_model",
    "llm_reasoning_effort",
    "vision_use_same_model",
    "vision_model",
    "embedding_mode",
    "embedding_base_url",
    "embedding_model",
    "embedding_auto_model",
    "search_engine_url",
    "timezone",
    "max_history_messages",
    "assistant_style",
    "weather_base_url",
    "github_username",
    "qq_email_address",
}


class RuntimeSettingsService:
    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self.secret_store = secret_store or create_secret_store()
        self._lock = RLock()
        self._settings_path: Path | None = None
        self._secret_disabled = {name: False for name in SECRET_FIELDS}

    def _path_for(self, settings: Any) -> Path:
        return Path(settings.data_dir) / "settings.json"

    def load_into(self, settings: Any) -> None:
        """Apply persisted non-secret overrides and OS credentials in-place."""
        with self._lock:
            path = self._path_for(settings)
            self._settings_path = path
            payload: dict[str, Any] = {}
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    logger.warning("Unable to load runtime settings: %s", exc)

            for name, value in payload.get("config", {}).items():
                if name in PERSISTED_FIELDS and value is not None:
                    setattr(settings, name, value)

            if not payload.get("config", {}).get("provider"):
                base_url = settings.llm_base_url.lower()
                if "api.openai.com" in base_url:
                    settings.provider = "openai"
                elif "api.myjarvis.ai" in base_url or "api.aijws.com" in base_url:
                    settings.provider = "my_jarvis"
                else:
                    settings.provider = "custom"

            disabled = payload.get("secret_disabled", {})
            for name in self._secret_disabled:
                self._secret_disabled[name] = bool(disabled.get(name, False))

            self._load_secret(settings, LLM_SECRET)
            self._load_secret(settings, EMBEDDING_SECRET)
            self._load_secret(settings, GITHUB_SECRET)
            self._load_secret(settings, NOTION_SECRET)
            self._load_secret(settings, QQ_EMAIL_SECRET)
            self._load_secret(settings, WEATHER_SECRET)

            # The control-plane host has a live OpenAI-compatible endpoint.
            # Migrate the earlier marketing endpoint and its legacy model once.
            migrated = False
            if (
                settings.provider == "my_jarvis"
                and settings.llm_base_url.rstrip("/")
                == "https://api.myjarvis.ai/v1"
            ):
                settings.llm_base_url = "https://api.aijws.com/v1"
                migrated = True
            if (
                settings.provider == "my_jarvis"
                and settings.llm_model == "deepseek-v4-flash"
            ):
                settings.llm_model = "gpt-5.6-terra"
                migrated = True
            if migrated:
                self._write(settings)

    def _load_secret(self, settings: Any, name: str) -> None:
        if self._secret_disabled[name]:
            setattr(settings, name, "")
            return
        try:
            stored = self.secret_store.get(name)
        except Exception as exc:
            logger.warning("Unable to read %s from credential storage: %s", name, exc)
            return
        if stored:
            setattr(settings, name, stored)

    def public_dict(self, settings: Any) -> dict[str, Any]:
        return {
            "provider": settings.provider,
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "llm_reasoning_effort": settings.llm_reasoning_effort,
            "vision_use_same_model": settings.vision_use_same_model,
            "vision_model": settings.vision_model,
            "embedding_mode": settings.embedding_mode,
            "embedding_base_url": settings.embedding_base_url,
            "embedding_model": settings.embedding_model,
            "embedding_auto_model": settings.embedding_auto_model,
            "llm_api_key_configured": bool(settings.llm_api_key),
            "embedding_api_key_configured": bool(settings.embedding_api_key),
            "github_token_configured": bool(settings.github_token),
            "notion_token_configured": bool(settings.notion_token),
            "qq_email_auth_code_configured": bool(settings.qq_email_auth_code),
            "weather_api_key_configured": bool(settings.weather_api_key),
            "search_engine_url": settings.search_engine_url,
            "timezone": settings.timezone,
            "max_history_messages": settings.max_history_messages,
            "assistant_style": settings.assistant_style,
            "weather_base_url": settings.weather_base_url,
            "github_username": settings.github_username,
            "qq_email_address": settings.qq_email_address,
            "needs_setup": not bool(
                settings.llm_api_key and settings.llm_base_url and settings.llm_model
            ),
        }

    def update(
        self,
        settings: Any,
        values: dict[str, Any],
        *,
        llm_api_key: str | None = None,
        embedding_api_key: str | None = None,
        github_token: str | None = None,
        notion_token: str | None = None,
        qq_email_auth_code: str | None = None,
        weather_api_key: str | None = None,
        clear_llm_api_key: bool = False,
        clear_embedding_api_key: bool = False,
        clear_github_token: bool = False,
        clear_notion_token: bool = False,
        clear_qq_email_auth_code: bool = False,
        clear_weather_api_key: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            old_fields = {name: getattr(settings, name) for name in PERSISTED_FIELDS}
            old_disabled = dict(self._secret_disabled)
            old_secrets = {
                LLM_SECRET: self.secret_store.get(LLM_SECRET),
                EMBEDDING_SECRET: self.secret_store.get(EMBEDDING_SECRET),
            }
            try:
                for name, value in values.items():
                    if name in PERSISTED_FIELDS and value is not None:
                        setattr(settings, name, value)

                self._update_secret(
                    settings, LLM_SECRET, llm_api_key, clear_llm_api_key
                )
                self._update_secret(
                    settings,
                    EMBEDDING_SECRET,
                    embedding_api_key,
                    clear_embedding_api_key,
                )
                self._update_secret(
                    settings, GITHUB_SECRET, github_token, clear_github_token
                )
                self._update_secret(
                    settings, NOTION_SECRET, notion_token, clear_notion_token
                )
                self._update_secret(
                    settings,
                    QQ_EMAIL_SECRET,
                    qq_email_auth_code,
                    clear_qq_email_auth_code,
                )
                self._update_secret(
                    settings, WEATHER_SECRET, weather_api_key, clear_weather_api_key
                )
                self._write(settings)
                return self.public_dict(settings)
            except Exception:
                for name, value in old_fields.items():
                    setattr(settings, name, value)
                self._secret_disabled = old_disabled
                for name, value in old_secrets.items():
                    try:
                        if value is None:
                            self.secret_store.delete(name)
                        else:
                            self.secret_store.set(name, value)
                    except Exception:
                        logger.exception("Unable to roll back credential %s", name)
                raise

    def _update_secret(
        self,
        settings: Any,
        name: str,
        value: str | None,
        clear: bool,
    ) -> None:
        if clear:
            self.secret_store.delete(name)
            self._secret_disabled[name] = True
            setattr(settings, name, "")
            return
        if value:
            self.secret_store.set(name, value)
            self._secret_disabled[name] = False
            setattr(settings, name, value)

    def _write(self, settings: Any) -> None:
        path = self._settings_path or self._path_for(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SETTINGS_VERSION,
            "config": {
                name: getattr(settings, name) for name in sorted(PERSISTED_FIELDS)
            },
            "secret_disabled": dict(self._secret_disabled),
        }
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)


runtime_settings = RuntimeSettingsService()
