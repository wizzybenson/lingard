"""Retrieval scoring and a deterministic offline embedder. Pure functions, no I/O."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent_memory.models import MemoryItem


class Embedder(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class RetrievalWeights:
    """score = similarity·w_sim + recency·w_recency + importance·w_importance."""

    similarity: float = 1.0
    recency: float = 0.5
    importance: float = 0.5
    recency_half_life_hours: float = 72.0


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"embedding size mismatch {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def recency(item: MemoryItem, now: datetime, half_life_hours: float) -> float:
    reference = item.last_accessed_at or item.created_at
    hours = max((now - reference).total_seconds() / 3600, 0.0)
    return float(0.5 ** (hours / half_life_hours))


def score(
    item: MemoryItem, query: list[float] | None, now: datetime, weights: RetrievalWeights
) -> tuple[float, float | None]:
    similarity = cosine(query, item.embedding) if query is not None and item.embedding is not None else None
    total = weights.recency * recency(item, now, weights.recency_half_life_hours) + weights.importance * item.importance
    if similarity is not None:
        total += weights.similarity * similarity
    return total, similarity


_TOKEN = re.compile(r"[\w']+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return _TOKEN.findall(stripped)


class HashingEmbedder:
    """Feature-hashed bag of words and character trigrams. Deterministic and offline, for tests and local dev.

    Production plugs a real embedding model in through ``Embedder``; this library never calls one itself.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dimensions, 1.0 if (value >> 63) & 1 else -1.0

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            features = [f"w:{token}"] + [f"c:{token[i : i + 3]}" for i in range(max(len(token) - 2, 0))]
            for feature in features:
                index, sign = self._bucket(feature)
                vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector
