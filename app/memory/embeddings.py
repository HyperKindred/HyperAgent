"""Embedding utilities — DeepSeek API + cosine similarity.

Generates vector embeddings for memory content so we can do semantic (RAG)
search instead of keyword matching.
"""

from __future__ import annotations

import logging
import json
import time
from typing import TYPE_CHECKING

import requests

from app.config import settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.memory.models import Memory


# ── shared session ──────────────────────────────────────────────────

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


# ── API call ─────────────────────────────────────────────────────────


def get_embedding(
    text: str,
    max_retries: int = 3,
    timeout: int = 30,
) -> list[float]:
    """Generate an embedding vector via the DeepSeek Embedding API.

    Uses the OpenAI-compatible ``/v1/embeddings`` endpoint with
    exponential-backoff retry on transient failures.
    """
    session = _get_session()

    for attempt in range(max_retries):
        try:
            api_key = settings.embedding_api_key or settings.deepseek_api_key
            if not api_key:
                logger.error("No API key configured for embeddings (embedding_api_key or deepseek_api_key)")
                return None
            resp = session.post(
                f"{settings.embedding_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.embedding_model, "input": text},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except requests.RequestException:
            if attempt == max_retries - 1:
                logger.warning("Embedding API failed after %d retries", max_retries)
                return None
            time.sleep(2**attempt)  # exponential backoff: 1s, 2s, 4s…

    return None


# ── similarity ───────────────────────────────────────────────────────


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (0 = orthogonal, 1 = identical)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── top-K retrieval ──────────────────────────────────────────────────


def rank_by_similarity(
    query: str, memories: list[Memory], top_k: int = 5
) -> list[tuple[float, Memory]]:
    """Embed ``query`` and return the ``top_k`` memories ranked by similarity.

    Skips memories without an embedding.  Returns ``(score, memory)`` pairs.
    """
    query_emb = get_embedding(query)
    if query_emb is None:
        return [(0.0, m) for m in memories[:top_k]]

    scored: list[tuple[float, Memory]] = []
    for mem in memories:
        if not mem.embedding:
            continue
        stored_emb = json.loads(mem.embedding)
        sim = cosine_similarity(query_emb, stored_emb)
        scored.append((sim, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


