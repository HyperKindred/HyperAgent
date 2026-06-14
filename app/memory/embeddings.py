"""Embedding utilities — DeepSeek API + cosine similarity.

Generates vector embeddings for memory content so we can do semantic (RAG)
search instead of keyword matching.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

from app.config import settings

if TYPE_CHECKING:
    from app.memory.models import Memory


# ── API call ─────────────────────────────────────────────────────────


def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector via the DeepSeek Embedding API.

    Uses the OpenAI-compatible ``/v1/embeddings`` endpoint so no extra
    SDKs or dependencies are needed.

    Raises ``requests.RequestException`` on API failure.
    """
    resp = requests.post(
        f"{settings.deepseek_base_url}/embeddings",
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": "deepseek-embedding", "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


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

    scored: list[tuple[float, Memory]] = []
    for mem in memories:
        if not mem.embedding:
            continue
        stored_emb = json.loads(mem.embedding)
        sim = cosine_similarity(query_emb, stored_emb)
        scored.append((sim, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]
