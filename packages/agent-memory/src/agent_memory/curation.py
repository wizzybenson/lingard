"""Deterministic curation: expiry, near-duplicate merging, per-namespace caps. No model calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agent_memory.models import MemoryItem, MemoryKind, Namespace, utcnow
from agent_memory.retrieval import RetrievalWeights, cosine, recency
from agent_memory.store import MemoryStore


@dataclass(frozen=True)
class CurationPolicy:
    duplicate_similarity: float = 0.92
    max_items_per_kind: int = 500
    weights: RetrievalWeights = field(default_factory=RetrievalWeights)


@dataclass(frozen=True)
class CurationReport:
    expired: int
    merged: int
    evicted: int


def _keep_value(item: MemoryItem, now: datetime, policy: CurationPolicy) -> float:
    return item.importance + recency(item, now, policy.weights.recency_half_life_hours) + 0.05 * item.access_count


async def curate(
    store: MemoryStore, namespace: Namespace, policy: CurationPolicy | None = None, *, now: datetime | None = None
) -> CurationReport:
    rules = policy or CurationPolicy()
    moment = now or utcnow()
    items = await store.list_items(namespace)
    expired = merged = evicted = 0

    live: list[MemoryItem] = []
    for item in items:
        if item.expired(moment):
            await store.delete(item.id)
            expired += 1
        else:
            live.append(item)

    kept: list[MemoryItem] = []
    for item in sorted(live, key=lambda i: i.created_at):
        twin = next(
            (
                k
                for k in kept
                if k.kind == item.kind
                and k.namespace == item.namespace
                and k.embedding is not None
                and item.embedding is not None
                and cosine(k.embedding, item.embedding) >= rules.duplicate_similarity
            ),
            None,
        )
        if twin is None:
            kept.append(item)
            continue
        survivor = twin.model_copy(
            update={
                "importance": max(twin.importance, item.importance),
                "access_count": twin.access_count + item.access_count,
                "tags": sorted(set(twin.tags) | set(item.tags)),
                "last_accessed_at": max(
                    d for d in (twin.last_accessed_at, item.last_accessed_at, item.created_at) if d is not None
                ),
            }
        )
        kept[kept.index(twin)] = survivor
        await store.put(survivor)
        await store.delete(item.id)
        merged += 1

    for kind in MemoryKind:
        of_kind = [i for i in kept if i.kind == kind]
        if len(of_kind) > rules.max_items_per_kind:
            of_kind.sort(key=lambda i: _keep_value(i, moment, rules))
            for item in of_kind[: len(of_kind) - rules.max_items_per_kind]:
                await store.delete(item.id)
                evicted += 1

    return CurationReport(expired=expired, merged=merged, evicted=evicted)
