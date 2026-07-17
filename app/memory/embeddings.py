"""OpenAI-compatible embeddings with provider fallback and metadata."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

from app.config import settings

if TYPE_CHECKING:
    from app.memory.models import Memory

logger = logging.getLogger(__name__)
MAX_EMBEDDING_CHARS = 24_000
_AUTO_PROBE_TTL = 300


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    api_key: str
    model: str
    source: str

    @property
    def fingerprint(self) -> str:
        value = f"{self.base_url.rstrip('/').lower()}|{self.model}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    dimensions: int
    fingerprint: str
    source: str


_session: requests.Session | None = None
_auto_unavailable_until: dict[str, float] = {}


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def reset_embedding_probe() -> None:
    _auto_unavailable_until.clear()


def _embedding_candidates() -> list[EmbeddingConfig]:
    if settings.embedding_mode == "disabled":
        return []

    candidates: list[EmbeddingConfig] = []
    if settings.embedding_mode == "auto" and settings.llm_api_key:
        auto = EmbeddingConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.embedding_auto_model,
            source="chat_provider",
        )
        if _auto_unavailable_until.get(auto.fingerprint, 0) <= time.monotonic():
            candidates.append(auto)

    fallback_key = settings.embedding_api_key
    if not fallback_key and settings.embedding_base_url == settings.deepseek_base_url:
        fallback_key = settings.deepseek_api_key
    if fallback_key:
        fallback = EmbeddingConfig(
            base_url=settings.embedding_base_url,
            api_key=fallback_key,
            model=settings.embedding_model,
            source="separate",
        )
        if not any(c.fingerprint == fallback.fingerprint for c in candidates):
            candidates.append(fallback)
    return candidates


def _request_embedding(
    config: EmbeddingConfig, text: str, *, timeout: int, retries: int
) -> list[float] | None:
    for attempt in range(retries):
        try:
            response = _get_session().post(
                f"{config.base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": config.model, "input": text},
                timeout=timeout,
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
            if isinstance(vector, list) and vector:
                return vector
            return None
        except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    return None


def get_embedding_result(
    text: str, max_retries: int = 3, timeout: int = 30
) -> EmbeddingResult | None:
    """Return a vector plus the exact provider/model identity that created it."""
    text = text[:MAX_EMBEDDING_CHARS]
    candidates = _embedding_candidates()
    if not candidates:
        logger.info("Embedding is disabled or has no configured API key")
        return None

    for config in candidates:
        retries = 1 if config.source == "chat_provider" else max_retries
        vector = _request_embedding(config, text, timeout=timeout, retries=retries)
        if vector is not None:
            return EmbeddingResult(
                vector=vector,
                model=config.model,
                dimensions=len(vector),
                fingerprint=config.fingerprint,
                source=config.source,
            )
        if config.source == "chat_provider":
            _auto_unavailable_until[config.fingerprint] = (
                time.monotonic() + _AUTO_PROBE_TTL
            )
            logger.info("Chat provider has no usable embedding endpoint; using fallback")

    logger.warning("All configured embedding providers failed")
    return None


def get_embedding(
    text: str, max_retries: int = 3, timeout: int = 30
) -> list[float] | None:
    result = get_embedding_result(text, max_retries=max_retries, timeout=timeout)
    return result.vector if result else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"Vector dimension mismatch: a={len(a)}, b={len(b)}. "
            "Both vectors must have the same length for cosine similarity."
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_similarity(
    query: str, memories: list, top_k: int = 5
) -> list[tuple[float, "Memory"]]:
    result = get_embedding_result(query)
    if result is None:
        return [(0.0, memory) for memory in memories[:top_k]]

    scored: list[tuple[float, Memory]] = []
    for memory in memories:
        if (
            not memory.embedding
            or memory.embedding_fingerprint != result.fingerprint
            or memory.embedding_dimensions != result.dimensions
        ):
            continue
        stored = json.loads(memory.embedding)
        scored.append((cosine_similarity(result.vector, stored), memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_k]

