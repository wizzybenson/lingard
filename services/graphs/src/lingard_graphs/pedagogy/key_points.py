"""The key-points path (SPEC §16): the grammar a learner is taught before a scene asks for it.

Nobody speaks well without the rules, so every grammar node up to the learner's level is a short lesson, in an order
where prerequisites come first. Nodes at the learner's own level are *core*: Today sends the learner to them before
the next story day. Lower ones are a refresher the learner may take; the next level's are a preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from lingard_contracts.common import Language
from lingard_curriculum.graph import CurriculumGraph
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.seed import load_seed

FIRST_BAND = 4
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

    for node in sorted(nodes, key=lambda n: (n.band, order.get(n.key, len(order)))):
        place(node, frozenset())
    return out


async def key_points_path(
    curriculum: CurriculumGraph, content_root: Path, language: Language, band: int | None
) -> list[KeyPointStep]:
    level = max(FIRST_BAND, band or FIRST_BAND)
    nodes = await curriculum.nodes(language, kinds=["grammar"], max_band=level + 1)
    prereqs = {n.key: [e.to_key for e in await curriculum.edges(n.key, "prereq")] for n in nodes}
    steps = ordered(nodes, prereqs, authored_order(content_root, language))
    return [KeyPointStep(node=n, core=n.band == level, preview=n.band > level) for n in steps]
