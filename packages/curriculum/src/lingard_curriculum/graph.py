"""``CurriculumGraph`` interface and in-memory implementation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from lingard_contracts.common import Language
from lingard_curriculum.models import CurriculumEdge, CurriculumNode, EdgeKind, NodeKind


class CurriculumGraph(Protocol):
    async def get(self, key: str) -> CurriculumNode | None: ...

    async def nodes(
        self,
        language: Language,
        *,
        kinds: Iterable[NodeKind] = (),
        max_band: int | None = None,
        band: int | None = None,
        reviewed_only: bool = True,
    ) -> list[CurriculumNode]: ...

    async def edges(
        self, key: str, kind: EdgeKind | None = None, *, direction: str = "out"
    ) -> list[CurriculumEdge]: ...

    async def upsert_node(self, node: CurriculumNode) -> CurriculumNode: ...

    async def upsert_edge(self, edge: CurriculumEdge) -> None: ...

    async def mark_reviewed(self, key: str, reviewer: str) -> CurriculumNode: ...

    async def unmark_reviewed(self, key: str) -> CurriculumNode: ...


class InMemoryCurriculumGraph:
    def __init__(self, nodes: Iterable[CurriculumNode] = (), edges: Iterable[CurriculumEdge] = ()) -> None:
        self._nodes = {n.key: n for n in nodes}
        self._edges: set[CurriculumEdge] = set(edges)

    async def get(self, key: str) -> CurriculumNode | None:
        return self._nodes.get(key)

    async def nodes(
        self,
        language: Language,
        *,
        kinds: Iterable[NodeKind] = (),
        max_band: int | None = None,
        band: int | None = None,
        reviewed_only: bool = True,
    ) -> list[CurriculumNode]:
        wanted = set(kinds)
        return sorted(
            (
                n
                for n in self._nodes.values()
                if n.language == language
                and (not wanted or n.kind in wanted)
                and (max_band is None or n.band <= max_band)
                and (band is None or n.band == band)
                and (n.reviewed or not reviewed_only)
            ),
            key=lambda n: (n.band, n.key),
        )

    async def edges(self, key: str, kind: EdgeKind | None = None, *, direction: str = "out") -> list[CurriculumEdge]:
        def end(edge: CurriculumEdge) -> str:
            return edge.from_key if direction == "out" else edge.to_key

        return sorted(
            (e for e in self._edges if end(e) == key and (kind is None or e.kind == kind)),
            key=lambda e: (e.kind, e.from_key, e.to_key),
        )

    async def upsert_node(self, node: CurriculumNode) -> CurriculumNode:
        existing = self._nodes.get(node.key)
        if existing is not None and existing.model_dump(
            exclude={"version", "reviewed", "reviewed_by"}
        ) != node.model_dump(exclude={"version", "reviewed", "reviewed_by"}):
            node = node.model_copy(update={"version": existing.version + 1, "reviewed": False, "reviewed_by": None})
        elif existing is not None:
            node = existing
        self._nodes[node.key] = node
        return node

    async def upsert_edge(self, edge: CurriculumEdge) -> None:
        self._edges.add(edge)

    async def mark_reviewed(self, key: str, reviewer: str) -> CurriculumNode:
        node = self._nodes[key].model_copy(update={"reviewed": True, "reviewed_by": reviewer})
        self._nodes[key] = node
        return node

    async def unmark_reviewed(self, key: str) -> CurriculumNode:
        node = self._nodes[key].model_copy(update={"reviewed": False, "reviewed_by": None})
        self._nodes[key] = node
        return node
