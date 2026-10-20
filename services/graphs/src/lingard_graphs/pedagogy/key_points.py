"""The key-points path (SPEC §16): what a learner is taught before a scene asks for it.

Nobody speaks well without the rules, so every grammar node up to the learner's level is a short lesson, in an order
where prerequisites come first; the words (vocabulary sets) and the ways of saying things (functions) of each level
are lessons too. Nodes at the learner's own level are *core*: Today sends the learner to the core grammar before the
next story day, and offers the core words and phrases beside it. Lower ones are a refresher; the next level's a preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from lingard_contracts.common import Language
from lingard_curriculum.graph import CurriculumGraph
from lingard_curriculum.models import CurriculumNode, NodeKind
from lingard_curriculum.seed import load_seed

FIRST_BAND = 4
KINDS: tuple[NodeKind, ...] = ("grammar", "lexset", "function")
"""What the path teaches; grammar comes first within a level, then the words, then the phrases."""
"""The lowest band the curriculum teaches; a learner without a placement starts here."""


@dataclass(frozen=True)
class KeyPointStep:
    node: CurriculumNode
    core: bool
    """At the learner's own level: taught before the next story day."""
    preview: bool
    """One level up: open to look ahead, never required."""


@cache
def authored_order(content_root: Path, language: Language) -> dict[str, int]:
    """Each node's place in the curriculum files, which are written in teaching order."""
    return {n.key: i for i, n in enumerate(load_seed(content_root, language).nodes)}


def ordered(nodes: list[CurriculumNode], prereqs: dict[str, list[str]], order: dict[str, int]) -> list[CurriculumNode]:
    """Band by band, prerequisites before what needs them; otherwise in the authored order."""
    by_key = {n.key: n for n in nodes}
    placed: set[str] = set()
    out: list[CurriculumNode] = []

    def place(node: CurriculumNode, trail: frozenset[str]) -> None:
        if node.key in placed or node.key in trail:
            return
        for before in prereqs.get(node.key, []):
            if before in by_key:
                place(by_key[before], trail | {node.key})
        placed.add(node.key)
        out.append(node)

    kinds = {kind: i for i, kind in enumerate(KINDS)}
    for node in sorted(nodes, key=lambda n: (n.band, kinds.get(n.kind, len(kinds)), order.get(n.key, len(order)))):
        place(node, frozenset())
    return out


async def key_points_path(
    curriculum: CurriculumGraph, content_root: Path, language: Language, band: int | None
) -> list[KeyPointStep]:
    level = max(FIRST_BAND, band or FIRST_BAND)
    nodes = await curriculum.nodes(language, kinds=list(KINDS), max_band=level + 1)
    prereqs = {n.key: [e.to_key for e in await curriculum.edges(n.key, "prereq")] for n in nodes}
    steps = ordered(nodes, prereqs, authored_order(content_root, language))
    return [KeyPointStep(node=n, core=n.band == level, preview=n.band > level) for n in steps]
