"""Load curriculum seed YAML from ``content/curriculum/<language>/`` into nodes and edges."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lingard_contracts.common import Language
from lingard_curriculum.conjugation import EnglishConjugator, FrenchConjugator
from lingard_curriculum.graph import CurriculumGraph
from lingard_curriculum.models import CurriculumEdge, CurriculumNode, EdgeKind

SEED_REVIEWER = "seed:lingard-content-v1"
_EDGE_FIELDS: tuple[EdgeKind, ...] = ("requires", "prereq")
_AUTO_REQUIRE_KINDS = {
    "speaking": ("function", "grammar", "lexset"),
    "writing": ("function", "grammar", "lexset"),
    "listening": ("function", "lexset"),
    "reading": ("function", "lexset"),
}


@dataclass
class SeedBundle:
    nodes: list[CurriculumNode] = field(default_factory=list)
    edges: list[CurriculumEdge] = field(default_factory=list)

    def by_key(self) -> dict[str, CurriculumNode]:
        return {n.key: n for n in self.nodes}


def _read(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


def _conjugation_nodes(language: Language, path: Path, reviewed: bool) -> list[CurriculumNode]:
    data = _read(path)
    common = {
        "kind": "conj_cell",
        "language": language,
        "source_url": data["source_url"],
        "as_of": str(data["as_of"]),
        "reviewed": reviewed,
        "reviewed_by": SEED_REVIEWER if reviewed else None,
    }
    nodes = []
    if language == "fr":
        fr = FrenchConjugator.load(path)
        for verb_key, verb in fr.verbs.items():
            for tense in fr.tenses:
                nodes.append(
                    CurriculumNode(
                        key=f"fr.conj.{verb_key}.{tense}",
                        band=fr.tense_bands[tense],
                        skill="writing",
                        title=f"{verb.infinitive} — {tense.replace('_', ' ')}",
                        payload={"verb": verb.infinitive, "tense": tense, "forms": fr.with_subjects(verb_key, tense)},
                        **common,
                    )
                )
    else:
        en = EnglishConjugator.load(path)
        bands: dict[str, int] = data["tense_bands"]
        for verb_key in en.verbs:
            base, past, participle = en.principal_parts(verb_key)
            nodes.append(
                CurriculumNode(
                    key=f"en.conj.{verb_key}.principal_parts",
                    band=bands["past_simple"],
                    skill="writing",
                    title=f"{base} — {past} — {participle}",
                    payload={"base": base, "past": past, "participle": participle},
                    **common,
                )
            )
    return nodes


def load_seed(content_root: str | Path, language: Language, *, mark_reviewed: bool = True) -> SeedBundle:
    folder = Path(content_root) / "curriculum" / language
    bundle = SeedBundle()
    pending_auto: list[CurriculumNode] = []
    pending_exercises: list[tuple[str, str]] = []

    for path in sorted(folder.glob("*.yaml")):
        if path.name == "conjugation.yaml":
            continue
        data = _read(path)
        defaults = dict(data.get("defaults", {}))
        auto = data.get("auto_requires")
        for raw in data["nodes"]:
            entry = {**defaults, **raw}
            edges = {name: entry.pop(name, []) for name in _EDGE_FIELDS}
            assessed_by = entry.pop("assessed_by", [])
            exercises_skill = entry.pop("exercises_skill", None)
            entry["as_of"] = str(entry["as_of"])
            node = CurriculumNode(**entry, reviewed=mark_reviewed, reviewed_by=SEED_REVIEWER if mark_reviewed else None)
            bundle.nodes.append(node)
            for kind, targets in edges.items():
                bundle.edges.extend(CurriculumEdge(from_key=node.key, to_key=t, kind=kind) for t in targets)
            for dimension in assessed_by:
                bundle.edges.append(CurriculumEdge(from_key=node.key, to_key=dimension, kind="assessed_by"))
            if exercises_skill:
                pending_exercises.append((node.key, exercises_skill))
            if auto == "same_band":
                pending_auto.append(node)

    conjugation = folder / "conjugation.yaml"
    if conjugation.is_file():
        bundle.nodes.extend(_conjugation_nodes(language, conjugation, mark_reviewed))

    for cando in pending_auto:
        assert cando.skill is not None
        kinds = _AUTO_REQUIRE_KINDS[cando.skill.value]
        for node in bundle.nodes:
            if node.kind in kinds and node.band == cando.band:
                bundle.edges.append(CurriculumEdge(from_key=cando.key, to_key=node.key, kind="requires"))

    for task_key, skill in pending_exercises:
        for node in bundle.nodes:
            if node.kind == "cando" and node.skill is not None and node.skill.value == skill:
                bundle.edges.append(CurriculumEdge(from_key=task_key, to_key=node.key, kind="exercises"))

    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: SeedBundle) -> None:
    """Every edge between curriculum nodes must resolve; rubric dimensions (``assessed_by``) are external keys."""
    keys = bundle.by_key()
    duplicates = [key for key, count in Counter(n.key for n in bundle.nodes).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate curriculum keys: {sorted(duplicates)}")
    for edge in bundle.edges:
        if edge.from_key not in keys:
            raise ValueError(f"edge from unknown node {edge.from_key}")
        if edge.kind != "assessed_by" and edge.to_key not in keys:
            raise ValueError(f"edge {edge.from_key} -[{edge.kind}]-> unknown node {edge.to_key}")
        if edge.kind == "prereq" and keys[edge.to_key].band > keys[edge.from_key].band:
            raise ValueError(f"prerequisite {edge.to_key} is at a higher band than {edge.from_key}")


async def seed_graph(graph: CurriculumGraph, bundle: SeedBundle) -> int:
    for node in bundle.nodes:
        stored = await graph.upsert_node(node)
        if node.reviewed and not stored.reviewed and stored.version == 1:
            await graph.mark_reviewed(node.key, node.reviewed_by or SEED_REVIEWER)
    for edge in bundle.edges:
        await graph.upsert_edge(edge)
    return len(bundle.nodes)


def lesson_gaps(bundle: SeedBundle) -> list[str]:
    """SPEC §16: every grammar node needs a lesson template before its band is playable."""
    return sorted(
        n.key
        for n in bundle.nodes
        if n.kind == "grammar" and not (isinstance(n.payload.get("lesson"), dict) and n.payload["lesson"].get("rule"))
    )
