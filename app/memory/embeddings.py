"""Embedding utilities — embedding API + cosine similarity.

Generates vector embeddings for memory content so we can do semantic (RAG)
search instead of keyword matching.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

import requests

from app.config import settings

if TYPE_CHECKING:
    from app.memory.models import Memory

logger = logging.getLogger(__name__)

# Max characters to send to the embedding API.
# Most embedding models have an 8K token limit (~32K chars for Chinese/English).
# Truncating before the API call prevents a silent failure that would store
# the memory with embedding=None and make it unsearchable.
MAX_EMBEDDING_CHARS = 24_000


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
) -> list[float] | None:
    """Generate an embedding vector via the configured Embedding API.

    Uses the OpenAI-compatible ``/v1/embeddings`` endpoint with
    exponential-backoff retry on transient failures.

    Returns ``None`` if the API is unavailable or unconfigured.
    """
    session = _get_session()

    # Truncate input to avoid exceeding the model's token limit
    text = text[:MAX_EMBEDDING_CHARS]

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
    """Cosine similarity between two vectors (0 = orthogonal, 1 = identical).

    Both vectors must have the same length; raises ``ValueError`` otherwise.
    """
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


# ── top-K retrieval ──────────────────────────────────────────────────


def rank_by_similarity(
    query: str, memories: list, top_k: int = 5
) -> list[tuple[float, "Memory"]]:
    """Embed ``query`` and return the ``top_k`` memories ranked by similarity.

    Skips memories without an embedding.  Returns ``(score, memory)`` pairs.
    """
    from app.memory.models import Memory
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


