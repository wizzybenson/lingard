"""Live-mode scorers for the calibration suites (real model calls; costs money)."""

from __future__ import annotations

import uuid
from typing import Any

from evals.framework import ROOT
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_CITY, LANGUAGE_PACK, Language, Skill
from lingard_contracts.events import TurnEvent
from lingard_curriculum.graph import InMemoryCurriculumGraph
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.agents.assessor import UtteranceAssessor
from lingard_graphs.agents.writing import WritingExaminer
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry


def _router() -> tuple[LLMRouter, PromptRegistry]:
    return LLMRouter(LLMConfig.load(ROOT / "config/llm.yaml")), PromptRegistry(ROOT / "prompts")


async def score_samples(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[str]]:
    router, prompts = _router()
    library = PackLibrary(ROOT / "content")
    examiner = WritingExaminer(router, prompts, ROOT / "content")
    predicted, human, packs = [], [], []
    for row in rows:
        if row["skill"] != "writing":
            continue
        pack = library.pack(row["pack"])
        task = next(t for t in pack.section_for(Skill.WRITING).tasks if t.id == row["task"])
        result = await examiner.score(
            pack=pack,
            conversion=library.conversion(row["pack"]),
            task=task,
            task_prompt=row["prompt"],
            response=row["response"],
            nodes={},
        )
        score = result.band_or_points
        if pack.scale.type == "points":
            score = float(library.conversion(row["pack"]).to_level(Skill.WRITING, score))
        predicted.append(score)
        scores = row.get("human_scores")
        human.append(sum(scores) / len(scores) if scores else float(row["target_band"]))
        packs.append(row["pack"])
    return predicted, human, packs


async def correction_run(language: Language, rows: list[dict[str, Any]]) -> tuple[int, int]:
    router, prompts = _router()
    curriculum = InMemoryCurriculumGraph()
    await seed_graph(curriculum, load_seed(ROOT / "content", language))
    nodes = {n.key: n for n in await curriculum.nodes(language)}
    pack = PackLibrary(ROOT / "content").pack(LANGUAGE_PACK[language])
    assessor = UtteranceAssessor(router, prompts)
    shown = correct = 0
    for row in rows:
        event = TurnEvent(
            trace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            scene_id=uuid.uuid4(),
            turn_index=0,
            speaker="learner",
            language=CITY_LOCALE[LANGUAGE_CITY[language]],
            transcript=row["text"],
        )
        result = await assessor.assess(
            event,
            pack=pack,
            language=language,
            learner_band=6,
            npc_name="a neighbour",
            nodes=nodes,
        )
        for tag in result.error_tags:
            if tag.showable:
                shown += 1
                accepted = {row.get("node_key"), *row.get("accept_node_keys", [])}
                correct += bool(row["has_error"]) and tag.node_key in accepted
    return shown, correct
