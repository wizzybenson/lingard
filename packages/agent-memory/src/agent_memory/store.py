"""Store interface, an in-memory implementation, and namespace-scoped views."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from agent_memory.models import MemoryItem, MemoryKind, Namespace, ScoredItem, utcnow
from agent_memory.retrieval import RetrievalWeights, score


@dataclass(frozen=True)
class Query:
    namespace: Namespace
    """Prefix match: ``("user", "u1")`` covers every namespace beneath it."""
    embedding: list[float] | None = None
    kinds: tuple[MemoryKind, ...] = ()
    tags: tuple[str, ...] = ()
    limit: int = 10
    min_score: float | None = None
    weights: RetrievalWeights = field(default_factory=RetrievalWeights)


def under(namespace: Namespace, prefix: Namespace) -> bool:
    return namespace[: len(prefix)] == prefix


class MemoryStore(Protocol):
    async def put(self, item: MemoryItem) -> MemoryItem: ...

    async def get(self, item_id: UUID) -> MemoryItem | None: ...

    async def search(self, query: Query, *, now: datetime | None = None) -> list[ScoredItem]: ...

    async def list_items(self, namespace: Namespace, kinds: Sequence[MemoryKind] = ()) -> list[MemoryItem]: ...

    async def delete(self, item_id: UUID) -> bool: ...

    async def delete_namespace(self, prefix: Namespace) -> int:
        """Remove every item under ``prefix``; used by account deletion. Returns the count removed."""
        ...


class InMemoryStore:
    """Reference implementation; also the contract the SQL store is tested against."""

    def __init__(self) -> None:
        self._items: dict[UUID, MemoryItem] = {}
        self._lock = asyncio.Lock()

    async def put(self, item: MemoryItem) -> MemoryItem:
        async with self._lock:
            self._items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> MemoryItem | None:
        return self._items.get(item_id)

    async def list_items(self, namespace: Namespace, kinds: Sequence[MemoryKind] = ()) -> list[MemoryItem]:
        return sorted(
            (i for i in self._items.values() if under(i.namespace, namespace) and (not kinds or i.kind in kinds)),
            key=lambda i: i.created_at,
        )

    async def search(self, query: Query, *, now: datetime | None = None) -> list[ScoredItem]:
        moment = now or utcnow()
        results: list[ScoredItem] = []
        for item in self._items.values():
            if not under(item.namespace, query.namespace) or item.expired(moment):
                continue
            if query.kinds and item.kind not in query.kinds:
                continue
            if query.tags and not set(query.tags) <= set(item.tags):
                continue
            total, similarity = score(item, query.embedding, moment, query.weights)
            if query.min_score is None or total >= query.min_score:
                results.append(ScoredItem(item=item, score=total, similarity=similarity))
        results.sort(key=lambda r: r.score, reverse=True)
        top = results[: query.limit]
        async with self._lock:
            for result in top:
                stored = self._items.get(result.item.id)
                if stored is not None:
                    self._items[stored.id] = stored.model_copy(
                        update={"last_accessed_at": moment, "access_count": stored.access_count + 1}
                    )
        return top

    async def delete(self, item_id: UUID) -> bool:
        async with self._lock:
            return self._items.pop(item_id, None) is not None

    async def delete_namespace(self, prefix: Namespace) -> int:
        async with self._lock:
            doomed = [i for i, item in self._items.items() if under(item.namespace, prefix)]
            for item_id in doomed:
                del self._items[item_id]
        return len(doomed)


class NamespaceViolationError(PermissionError):
    pass


class ScopedMemory:
    """A view that can only read and write inside allowed namespace prefixes.

    Lingard gives NPC actors a view over world memory only, so pedagogical memory is unreachable by construction.
    """

    def __init__(self, store: MemoryStore, allowed: Sequence[Namespace]) -> None:
        if not allowed:
            raise ValueError("a scoped view needs at least one allowed namespace")
        self._store = store
        self._allowed = tuple(allowed)

    def _check(self, namespace: Namespace) -> None:
        if not any(under(namespace, prefix) for prefix in self._allowed):
            raise NamespaceViolationError(f"namespace {namespace} is outside this view")

    async def put(self, item: MemoryItem) -> MemoryItem:
        self._check(item.namespace)
        return await self._store.put(item)

    async def search(self, query: Query, *, now: datetime | None = None) -> list[ScoredItem]:
        self._check(query.namespace)
        return await self._store.search(query, now=now)

    async def list_items(self, namespace: Namespace, kinds: Sequence[MemoryKind] = ()) -> list[MemoryItem]:
        self._check(namespace)
        return await self._store.list_items(namespace, kinds)
