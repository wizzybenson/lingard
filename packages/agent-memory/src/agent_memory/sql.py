"""Postgres + pgvector store (install ``agent-memory[postgres]``). Same contract as ``InMemoryStore``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    ColumnElement,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    and_,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_memory.models import MemoryItem, MemoryKind, Namespace, ScoredItem, utcnow
from agent_memory.retrieval import score
from agent_memory.store import Query

CANDIDATE_FACTOR = 5


def namespace_path(namespace: Namespace) -> str:
    """``("user","u1")`` → ``"user/u1/"``. The trailing slash makes prefix matching segment-exact."""
    if any("/" in part for part in namespace):
        raise ValueError("namespace segments may not contain '/'")
    return "/".join(namespace) + "/"


def memory_table(metadata: MetaData, dimensions: int, name: str = "memory_items") -> Table:
    return Table(
        name,
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("namespace", ARRAY(String), nullable=False),
        Column("namespace_path", Text, nullable=False, index=True),
        Column("kind", String(16), nullable=False, index=True),
        Column("content", Text, nullable=False),
        Column("data", JSONB, nullable=False),
        Column("tags", ARRAY(String), nullable=False),
        Column("embedding", Vector(dimensions), nullable=True),
        Column("importance", Float, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("last_accessed_at", DateTime(timezone=True), nullable=True),
        Column("access_count", Integer, nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=True),
    )


def _row(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "namespace": list(item.namespace),
        "namespace_path": namespace_path(item.namespace),
        "kind": item.kind.value,
        "content": item.content,
        "data": item.data,
        "tags": item.tags,
        "embedding": item.embedding,
        "importance": item.importance,
        "created_at": item.created_at,
        "last_accessed_at": item.last_accessed_at,
        "access_count": item.access_count,
        "expires_at": item.expires_at,
    }


def _item(row: Any) -> MemoryItem:
    embedding = row.embedding
    return MemoryItem(
        id=row.id,
        namespace=tuple(row.namespace),
        kind=MemoryKind(row.kind),
        content=row.content,
        data=row.data,
        tags=list(row.tags),
        embedding=[float(v) for v in embedding] if embedding is not None else None,
        importance=row.importance,
        created_at=row.created_at,
        last_accessed_at=row.last_accessed_at,
        access_count=row.access_count,
        expires_at=row.expires_at,
    )


class SqlMemoryStore:
    def __init__(self, engine: AsyncEngine, table: Table) -> None:
        self._engine = engine
        self._t = table

    async def put(self, item: MemoryItem) -> MemoryItem:
        row = _row(item)
        async with self._engine.begin() as conn:
            existing = await conn.execute(select(self._t.c.id).where(self._t.c.id == item.id))
            if existing.first() is None:
                await conn.execute(insert(self._t).values(**row))
            else:
                await conn.execute(update(self._t).where(self._t.c.id == item.id).values(**row))
        return item

    async def get(self, item_id: UUID) -> MemoryItem | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(select(self._t).where(self._t.c.id == item_id))).first()
        return _item(row) if row else None

    async def list_items(self, namespace: Namespace, kinds: Sequence[MemoryKind] = ()) -> list[MemoryItem]:
        conditions: list[ColumnElement[bool]] = [func.starts_with(self._t.c.namespace_path, namespace_path(namespace))]
        if kinds:
            conditions.append(self._t.c.kind.in_([k.value for k in kinds]))
        async with self._engine.connect() as conn:
            rows = await conn.execute(select(self._t).where(and_(*conditions)).order_by(self._t.c.created_at))
        return [_item(r) for r in rows]

    async def search(self, query: Query, *, now: datetime | None = None) -> list[ScoredItem]:
        moment = now or utcnow()
        t = self._t
        conditions: list[ColumnElement[bool]] = [
            func.starts_with(t.c.namespace_path, namespace_path(query.namespace)),
            or_(t.c.expires_at.is_(None), t.c.expires_at > moment),
        ]
        if query.kinds:
            conditions.append(t.c.kind.in_([k.value for k in query.kinds]))
        if query.tags:
            conditions.append(t.c.tags.contains(list(query.tags)))
        statement = select(t).where(and_(*conditions)).limit(query.limit * CANDIDATE_FACTOR)
        if query.embedding is not None:
            statement = statement.order_by(t.c.embedding.cosine_distance(query.embedding).nulls_last())
        else:
            statement = statement.order_by(t.c.importance.desc(), t.c.created_at.desc())
        async with self._engine.begin() as conn:
            candidates = [_item(r) for r in await conn.execute(statement)]
            scored = []
            for item in candidates:
                total, similarity = score(item, query.embedding, moment, query.weights)
                if query.min_score is None or total >= query.min_score:
                    scored.append(ScoredItem(item=item, score=total, similarity=similarity))
            scored.sort(key=lambda s: s.score, reverse=True)
            top = scored[: query.limit]
            if top:
                await conn.execute(
                    update(t)
                    .where(t.c.id.in_([s.item.id for s in top]))
                    .values(last_accessed_at=moment, access_count=t.c.access_count + 1)
                )
        return top

    async def delete(self, item_id: UUID) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(delete(self._t).where(self._t.c.id == item_id))
        return bool(result.rowcount)

    async def delete_namespace(self, prefix: Namespace) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(self._t).where(func.starts_with(self._t.c.namespace_path, namespace_path(prefix)))
            )
        return int(result.rowcount)
