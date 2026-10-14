"""Postgres implementation of ``CurriculumGraph`` (tables ``curriculum_nodes`` / ``curriculum_edges``, SPEC §7)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    ColumnElement,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from lingard_contracts.common import Language
from lingard_curriculum.models import CurriculumEdge, CurriculumNode, EdgeKind, NodeKind

_CONTENT_FIELDS = ("kind", "language", "band", "skill", "title", "payload", "source_url", "as_of")


def curriculum_tables(metadata: MetaData) -> tuple[Table, Table]:
    nodes = Table(
        "curriculum_nodes",
        metadata,
        Column("id", Uuid, primary_key=True, server_default=func.gen_random_uuid()),
        Column("key", String(160), nullable=False, unique=True),
        Column("kind", String(16), nullable=False, index=True),
        Column("language", String(2), nullable=False, index=True),
        Column("band", Integer, nullable=False, index=True),
        Column("skill", String(16), nullable=True),
        Column("title", Text, nullable=False),
        Column("payload", JSONB, nullable=False),
        Column("source_url", Text, nullable=False),
        Column("as_of", String(32), nullable=False),
        Column("version", Integer, nullable=False),
        Column("reviewed", Boolean, nullable=False),
        Column("reviewed_by", String(120), nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    )
    edges = Table(
        "curriculum_edges",
        metadata,
        Column("id", Uuid, primary_key=True, server_default=func.gen_random_uuid()),
        Column("from_key", String(160), nullable=False, index=True),
        Column("to_key", String(160), nullable=False, index=True),
        Column("kind", String(16), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
        UniqueConstraint("from_key", "to_key", "kind", name="uq_curriculum_edge"),
    )
    return nodes, edges


def _node(row: Any) -> CurriculumNode:
    return CurriculumNode(
        key=row.key,
        kind=row.kind,
        language=row.language,
        band=row.band,
        skill=row.skill,
        title=row.title,
        payload=row.payload,
        source_url=row.source_url,
        as_of=row.as_of,
        version=row.version,
        reviewed=row.reviewed,
        reviewed_by=row.reviewed_by,
    )


class SqlCurriculumGraph:
    def __init__(self, engine: AsyncEngine, nodes: Table, edges: Table) -> None:
        self._engine = engine
        self._n = nodes
        self._e = edges

    async def get(self, key: str) -> CurriculumNode | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(select(self._n).where(self._n.c.key == key))).first()
        return _node(row) if row else None

    async def nodes(
        self,
        language: Language,
        *,
        kinds: Iterable[NodeKind] = (),
        max_band: int | None = None,
        band: int | None = None,
        reviewed_only: bool = True,
    ) -> list[CurriculumNode]:
        n = self._n
        conditions: list[ColumnElement[bool]] = [n.c.language == language]
        wanted = list(kinds)
        if wanted:
            conditions.append(n.c.kind.in_(wanted))
        if max_band is not None:
            conditions.append(n.c.band <= max_band)
        if band is not None:
            conditions.append(n.c.band == band)
        if reviewed_only:
            conditions.append(n.c.reviewed.is_(True))
        async with self._engine.connect() as conn:
            rows = await conn.execute(select(n).where(and_(*conditions)).order_by(n.c.band, n.c.key))
        return [_node(r) for r in rows]

    async def edges(self, key: str, kind: EdgeKind | None = None, *, direction: str = "out") -> list[CurriculumEdge]:
        e = self._e
        column = e.c.from_key if direction == "out" else e.c.to_key
        conditions: list[ColumnElement[bool]] = [column == key]
        if kind is not None:
            conditions.append(e.c.kind == kind)
        async with self._engine.connect() as conn:
            rows = await conn.execute(select(e).where(and_(*conditions)).order_by(e.c.kind, e.c.from_key, e.c.to_key))
        return [CurriculumEdge(from_key=r.from_key, to_key=r.to_key, kind=r.kind) for r in rows]

    async def upsert_node(self, node: CurriculumNode) -> CurriculumNode:
        """A content change bumps the version and clears review, so edited nodes need re-review."""
        values = node.model_dump(mode="json")
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(self._n).where(self._n.c.key == node.key))).first()
            if row is None:
                await conn.execute(insert(self._n).values(**values))
                return node
            current = _node(row)
            if all(getattr(current, f) == getattr(node, f) for f in _CONTENT_FIELDS):
                return current
            bumped = node.model_copy(update={"version": current.version + 1, "reviewed": False, "reviewed_by": None})
            await conn.execute(
                update(self._n).where(self._n.c.key == node.key).values(**bumped.model_dump(mode="json"))
            )
            return bumped

    async def upsert_edge(self, edge: CurriculumEdge) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(pg_insert(self._e).values(**edge.model_dump()).on_conflict_do_nothing())

    async def _set_review(self, key: str, reviewed: bool, reviewer: str | None) -> CurriculumNode:
        statement = (
            update(self._n)
            .where(self._n.c.key == key)
            .values(reviewed=reviewed, reviewed_by=reviewer)
            .returning(self._n)
        )
        async with self._engine.begin() as conn:
            row = (await conn.execute(statement)).first()
        if row is None:
            raise KeyError(key)
        return _node(row)

    async def mark_reviewed(self, key: str, reviewer: str) -> CurriculumNode:
        return await self._set_review(key, True, reviewer)

    async def unmark_reviewed(self, key: str) -> CurriculumNode:
        return await self._set_review(key, False, None)
