"""Runtime model settings and provider capability checks."""

from __future__ import annotations

import base64
from typing import Literal
from urllib.parse import urlparse

import pytz
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.config import settings
from app.settings.service import runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])

_TINY_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zt9sAAAAASUVORK5CYII="
    )
).decode("ascii")


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    is_local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if parsed.scheme != "https" and not is_local_http:
        raise ValueError("Base URL 必须使用 HTTPS，本机开发地址除外")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Base URL 格式无效")
    return value


class SettingsUpdate(BaseModel):
    provider: Literal["my_jarvis", "openai", "custom"] | None = None
    llm_base_url: str | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=120)
    llm_reasoning_effort: Literal["none"] | None = None
    vision_use_same_model: bool | None = None
    vision_model: str | None = Field(default=None, max_length=120)
    embedding_mode: Literal["auto", "separate", "disabled"] | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = Field(default=None, max_length=160)
    embedding_auto_model: str | None = Field(default=None, max_length=160)
    search_engine_url: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    max_history_messages: int | None = Field(default=None, ge=0, le=500)
    assistant_style: Literal["concise", "balanced", "detailed"] | None = None
    weather_base_url: str | None = Field(default=None, max_length=500)
    github_username: str | None = Field(default=None, max_length=120)
    qq_email_address: str | None = Field(default=None, max_length=254)
    llm_api_key: SecretStr | None = None
    embedding_api_key: SecretStr | None = None
    github_token: SecretStr | None = None
    notion_token: SecretStr | None = None
    qq_email_auth_code: SecretStr | None = None
    weather_api_key: SecretStr | None = None
    clear_llm_api_key: bool = False
    clear_embedding_api_key: bool = False
    clear_github_token: bool = False
    clear_notion_token: bool = False
    clear_qq_email_auth_code: bool = False
    clear_weather_api_key: bool = False

    @field_validator("llm_base_url", "embedding_base_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return normalize_base_url(value) if value else value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value:
            try:
                pytz.timezone(value)
            except pytz.UnknownTimeZoneError as exc:
                raise ValueError("时区无效，请使用 IANA 名称，例如 Asia/Shanghai") from exc
        return value


class ProviderRequest(BaseModel):
    base_url: str
    api_key: SecretStr | None = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_base_url(value)


class CapabilityTestRequest(ProviderRequest):
    kind: Literal["chat", "vision", "embedding"]
    model: str = Field(min_length=1, max_length=160)


def _key_value(
    draft: SecretStr | None,
    stored: str,
    requested_base_url: str,
    stored_base_url: str,
) -> str:
    if draft:
        key = draft.get_secret_value().strip()
    elif requested_base_url.rstrip("/") == stored_base_url.rstrip("/"):
        key = stored.strip()
    else:
        key = ""
    if not key:
        raise HTTPException(
            status_code=400,
            detail="地址已改变，请输入该服务对应的 API Key",
        )
    return key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _provider_error(response: requests.Response) -> HTTPException:
    status = response.status_code
    if status in (401, 403):
        detail = "API Key 无效或无权访问该模型"
    elif status == 402:
        detail = "供应商账户余额不足"
    elif status == 404:
        detail = "接口地址或模型不存在"
    elif status == 429:
        detail = "请求过于频繁或供应商额度受限"
    elif 500 <= status:
        detail = "供应商服务暂时不可用"
    else:
        detail = "供应商拒绝了请求，可能是不兼容的模型参数"
    return HTTPException(status_code=429 if status == 429 else 400, detail=detail)


def _connection_error(exc: requests.RequestException, action: str) -> HTTPException:
    if isinstance(exc, requests.exceptions.SSLError):
        detail = "TLS 连接被服务端中断，请检查 Base URL"
    elif isinstance(exc, requests.exceptions.ConnectTimeout):
        detail = "连接供应商超时，请检查网络和 Base URL"
    elif isinstance(exc, requests.exceptions.ConnectionError):
        detail = "无法建立供应商连接，请检查 Base URL"
    else:
        detail = f"{action}失败，请稍后重试"
    return HTTPException(status_code=502, detail=detail)


def _post_json(
    url: str, api_key: str, payload: dict, *, timeout: int = 45
) -> dict:
    try:
        response = requests.post(
            url, headers=_headers(api_key), json=payload, timeout=timeout
        )
    except requests.RequestException as exc:
        raise _connection_error(exc, "调用供应商 API") from exc
    if not response.ok:
        raise _provider_error(response)
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="供应商返回了无效 JSON") from exc


def _post_stream(url: str, api_key: str, payload: dict) -> None:
    try:
        with requests.post(
            url,
            headers=_headers(api_key),
            json={**payload, "stream": True},
            timeout=45,
            stream=True,
        ) as response:
            if not response.ok:
                raise _provider_error(response)
            for line in response.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    return
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise _connection_error(exc, "建立流式响应") from exc
    raise HTTPException(status_code=502, detail="供应商没有返回 SSE 流式数据")


def _token_params(model: str) -> dict[str, object]:
    if model.lower().startswith("gpt-5.6"):
        return {"max_completion_tokens": 32, "reasoning_effort": "none"}
    return {"max_tokens": 32}


@router.get("")
def get_settings() -> dict:
    from app.memory.reindex import reindex_manager

    result = runtime_settings.public_dict(settings)
    result["reindex"] = reindex_manager.status()
    return result


@router.put("")
def update_settings(body: SettingsUpdate) -> dict:
    values = body.model_dump(
        exclude={
            "llm_api_key",
            "embedding_api_key",
            "github_token",
            "notion_token",
            "qq_email_auth_code",
            "weather_api_key",
            "clear_llm_api_key",
            "clear_embedding_api_key",
            "clear_github_token",
            "clear_notion_token",
            "clear_qq_email_auth_code",
            "clear_weather_api_key",
        },
        exclude_none=True,
    )
    try:
        result = runtime_settings.update(
            settings,
            values,
            llm_api_key=(
                body.llm_api_key.get_secret_value().strip()
                if body.llm_api_key
                else None
            ),
            embedding_api_key=(
                body.embedding_api_key.get_secret_value().strip()
                if body.embedding_api_key
                else None
            ),
            github_token=(
                body.github_token.get_secret_value().strip()
                if body.github_token
                else None
            ),
            notion_token=(
                body.notion_token.get_secret_value().strip()
                if body.notion_token
                else None
            ),
            qq_email_auth_code=(
                body.qq_email_auth_code.get_secret_value().strip()
                if body.qq_email_auth_code
                else None
            ),
            weather_api_key=(
                body.weather_api_key.get_secret_value().strip()
                if body.weather_api_key
                else None
            ),
            clear_llm_api_key=body.clear_llm_api_key,
            clear_embedding_api_key=body.clear_embedding_api_key,
            clear_github_token=body.clear_github_token,
            clear_notion_token=body.clear_notion_token,
            clear_qq_email_auth_code=body.clear_qq_email_auth_code,
            clear_weather_api_key=body.clear_weather_api_key,
        )
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail="保存系统凭据失败") from exc

    from app.agent.graph import reset_llm_cache
    from app.memory.embeddings import reset_embedding_probe

    reset_llm_cache()
    reset_embedding_probe()
    from app.memory.reindex import reindex_manager

    result["reindex"] = reindex_manager.status()
    return result


@router.post("/models")
def discover_models(body: ProviderRequest) -> dict:
    key = _key_value(
        body.api_key, settings.llm_api_key, body.base_url, settings.llm_base_url
    )
    try:
        response = requests.get(
            f"{body.base_url}/models", headers=_headers(key), timeout=20
        )
    except requests.RequestException as exc:
        raise _connection_error(exc, "获取模型列表") from exc
    if not response.ok:
        raise _provider_error(response)
    try:
        items = response.json().get("data", [])
        model_ids = sorted(
            {
                item.get("id")
                for item in items
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="模型列表响应格式无效") from exc
    return {"models": model_ids}


@router.post("/test")
def test_capability(body: CapabilityTestRequest) -> dict:
    stored_key = (
        settings.embedding_api_key
        if body.kind == "embedding"
        else settings.llm_api_key
    )
    stored_base_url = (
        settings.embedding_base_url
        if body.kind == "embedding"
        else settings.llm_base_url
    )
    key = _key_value(body.api_key, stored_key, body.base_url, stored_base_url)
    if body.kind == "embedding":
        data = _post_json(
            f"{body.base_url}/embeddings",
            key,
            {"model": body.model, "input": "HyperAgent connection test"},
        )
        vector = ((data.get("data") or [{}])[0]).get("embedding")
        if not isinstance(vector, list) or not vector:
            raise HTTPException(status_code=502, detail="Embedding 响应缺少向量数据")
        return {"ok": True, "checks": ["embedding"], "dimensions": len(vector)}

    content: list[dict[str, object]] = [
        {"type": "text", "text": "请只回复 OK"}
    ]
    if body.kind == "vision":
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{_TINY_PNG}",
                    "detail": "low",
                },
            }
        )
    payload: dict[str, object] = {
        "model": body.model,
        "messages": [{"role": "user", "content": content}],
        **_token_params(body.model),
    }
    if body.kind == "chat":
        _post_stream(f"{body.base_url}/chat/completions", key, payload)
    else:
        _post_json(f"{body.base_url}/chat/completions", key, payload)
    checks = ["chat", "vision"] if body.kind == "vision" else ["chat"]

    if body.kind == "chat":
        tool_payload = {
            "model": body.model,
            "messages": [{"role": "user", "content": "调用连接测试工具"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "hyperagent_connection_test",
                        "description": "Validate function tool support.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "hyperagent_connection_test"},
            },
            **_token_params(body.model),
        }
        tool_data = _post_json(
            f"{body.base_url}/chat/completions", key, tool_payload
        )
        try:
            tool_calls = tool_data["choices"][0]["message"]["tool_calls"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail="模型可以对话，但未通过函数调用测试"
            ) from exc
        if not tool_calls:
            raise HTTPException(status_code=400, detail="模型未返回函数调用")
        checks.append("tools")

    return {"ok": True, "checks": checks}


@router.post("/embedding/reindex")
def start_embedding_reindex() -> dict:
    from app.memory.reindex import reindex_manager

    return reindex_manager.start()


@router.get("/embedding/reindex")
def get_embedding_reindex() -> dict:
    from app.memory.reindex import reindex_manager

    return reindex_manager.status()
