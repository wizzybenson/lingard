"""Writing Examiner (SPEC §10): rubric-anchored with exemplars, three independent samples, median per criterion."""

from __future__ import annotations

import asyncio
import re
import statistics
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from lingard_contracts.assessment import DimensionScore, ErrorTag, WritingAssessment
from lingard_contracts.common import PackId, Skill
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.packs import Conversion, ExamPack, TaskDef
from lingard_graphs.agents.assessor import RawTag, locate
from lingard_llm import LLMRouter, PromptRegistry

EXAMS = {"tef_canada": "TEF Canada", "ielts_gt": "IELTS General Training"}
SAMPLES = 3


class _RawScore(BaseModel):
    dimension: str
    score: float
    rationale: str = ""


class _Raw(BaseModel):
    dimensions: list[_RawScore]
    errors: list[RawTag] = Field(default_factory=list)
    rewrite: str = ""


def word_count(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text, flags=re.UNICODE))


def round_half(value: float) -> float:
    return round(value * 2) / 2


def rubric_text(rubrics: dict[str, Any], criteria: list[str]) -> str:
    lines = []
    for criterion in criteria:
        levels = rubrics.get(criterion, {})
        described = "; ".join(f"{level}: {text}" for level, text in sorted(levels.items(), reverse=True))
        lines.append(f"- {criterion}: {described}")
    return "\n".join(lines)


class WritingExaminer:
    def __init__(self, router: LLMRouter, prompts: PromptRegistry, content_root: Path) -> None:
        self._router = router
        self._prompt = prompts.get("writing_examiner")
        self._content = content_root

    def _rubrics(self, pack: PackId) -> dict[str, Any]:
        data: dict[str, Any] = yaml.safe_load((self._content / "packs" / pack / "rubrics.yaml").read_text())
        writing: dict[str, Any] = data["writing"]
        return writing

    def _exemplars(self, pack: PackId, task: TaskDef) -> str:
        path = self._content / "packs" / pack / "exemplars.yaml"
        if not path.is_file():
            return "none available"
        data = yaml.safe_load(path.read_text()).get(task.id)
        if not data:
            return "none available"
        return "\n".join(f"[level {r['band']}] {r['text']}" for r in data["responses"])

    async def score(
        self,
        *,
        pack: ExamPack,
        conversion: Conversion,
        task: TaskDef,
        task_prompt: str,
        response: str,
        nodes: dict[str, CurriculumNode],
        trace_id: str | None = None,
    ) -> WritingAssessment:
        count = word_count(response)
        short = count < task.min_words
        text = self._prompt.render(
            exam=EXAMS[pack.id],
            task_name=task.id,
            task_prompt=task_prompt,
            min_words=task.min_words,
            word_count=count,
            length_note="The response is UNDER the minimum length: penalise task achievement accordingly."
            if short
            else "",
            scale=pack.scale_description,
            rubric=rubric_text(self._rubrics(pack.id), task.rubric),
            exemplars=self._exemplars(pack.id, task),
            response=response,
            candidate_nodes=", ".join(sorted(nodes)),
        )
        samples = await asyncio.gather(
            *(
                self._router.structured("frontier", self._prompt, _Raw, [HumanMessage(content=text)], trace_id=trace_id)
                for _ in range(SAMPLES)
            )
        )
        dimensions = []
        for criterion in task.rubric:
            values = [d.score for s in samples for d in s.dimensions if d.dimension == criterion]
            if not values:
                continue
            spread = max(values) - min(values)
            rationale = next((d.rationale for s in samples for d in s.dimensions if d.dimension == criterion), "")
            dimensions.append(
                DimensionScore(
                    dimension=criterion,
                    score=statistics.median(values),
                    confidence=max(0.3, 1 - spread / 3),
                    rationale=rationale,
                )
            )
        mean = statistics.fmean(d.score for d in dimensions) if dimensions else 0.0
        if pack.scale.type == "band":
            band_or_points = round_half(mean)
        else:
            band_or_points = conversion.min_score_for(Skill.WRITING, round(mean))
        tags: list[ErrorTag] = []
        seen: set[tuple[str, str]] = set()
        for sample in samples:
            for raw in sample.errors:
                span = locate(response, raw.span)
                key = (raw.node_key, raw.span.casefold())
                if span is None or raw.node_key not in nodes or key in seen:
                    continue
                agreeing = sum(
                    1
                    for s in samples
                    for e in s.errors
                    if e.node_key == raw.node_key and e.span.casefold() == raw.span.casefold()
                )
                seen.add(key)
                tags.append(
                    ErrorTag(
                        node_key=raw.node_key,
                        span=span,
                        correction=raw.correction,
                        explanation=raw.explanation,
                        severity=raw.severity,
                        confidence=raw.confidence,
                        second_check_agrees=agreeing >= 2,
                    )
                )  # independent samples double as the second check
        rewrite = max((s.rewrite for s in samples), key=len)
        return WritingAssessment(
            pack=pack.id,
            task_type=task.id,
            word_count=count,
            dimensions=dimensions,
            band_or_points=band_or_points,
            rewrite=rewrite,
            error_tags=tags,
            samples=SAMPLES,
            model_versions={"writing_examiner": self._prompt.ref},
        )
