"""Memory records. Working memory lives in the caller's state (e.g. LangGraph); this library holds the rest."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Namespace = tuple[str, ...]


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    """What happened: events, conversations, shared history."""
    SEMANTIC = "semantic"
    """Facts and knowledge: stable statements about the world or the learner."""
    PROCEDURAL = "procedural"
    """What works: strategies, preferences, habits that shape future behaviour."""


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    namespace: Namespace = Field(min_length=1)
    kind: MemoryKind
    content: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    importance: float = Field(default=0.5, ge=0, le=1)
    created_at: datetime = Field(default_factory=utcnow)
    last_accessed_at: datetime | None = None
    access_count: int = 0
    expires_at: datetime | None = None

    def expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now


class ScoredItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: MemoryItem
    score: float
    similarity: float | None = None
