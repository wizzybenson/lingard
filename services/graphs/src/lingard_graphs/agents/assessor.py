"""Utterance Assessor (SPEC §10, §12): turn → dimension scores and span-cited error tags mapped to curriculum nodes."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from lingard_contracts.assessment import DimensionScore, ErrorTag, Span, TargetEvidence, UtteranceAssessment
from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_PACK, LANGUAGE_SCALE, Language
from lingard_contracts.events import TurnEvent
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.packs import ExamPack
from lingard_llm import LLMRouter, PromptRegistry

SCALE_DESC = {"ielts_gt": "IELTS band 0–9 in half bands", "tef_canada": "NCLC level 1–12"}
EXAM_NAMES = {"tef_canada": "TEF Canada", "ielts_gt": "IELTS General Training"}


class RawTag(BaseModel):
    node_key: str
    span: str
    correction: str | None = None
    explanation: str | None = None
    severity: Literal["minor", "major", "intelligibility"] = "minor"
    confidence: float = Field(ge=0, le=1)


class RawEvidence(BaseModel):
    node_key: str
    correct: bool
    span: str | None = None
    confidence: float = Field(ge=0, le=1)


class RawScore(BaseModel):
    dimension: str
    score: float
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


class AssessorOutput(BaseModel):
    dimensions: list[RawScore]
    errors: list[RawTag] = Field(default_factory=list)
    target_evidence: list[RawEvidence] = Field(default_factory=list)
    band_estimate: float | None = None
    confidence: float = Field(ge=0, le=1)


class CheckVerdict(BaseModel):
    is_error: bool
    confidence: float = Field(ge=0, le=1)


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def locate(transcript: str, fragment: str) -> Span | None:
    """Exact (case/accent-insensitive) location of ``fragment``; None if the model cited text that isn't there."""
    if not fragment.strip():
        return None
    folded, needle = _fold(transcript), _fold(fragment.strip())
    index = folded.find(needle)
    if index < 0:
        collapsed = re.sub(r"[^\w']+", " ", needle).strip()
        match = re.search(r"\W+".join(map(re.escape, collapsed.split())), folded) if collapsed else None
        if match is None:
            return None
        index, end = match.start(), match.end()
    else:
        end = index + len(needle)
    return Span(start=index, end=end, text=transcript[index:end])


def rule_check(node: CurriculumNode | None, span: str) -> bool | None:
    """Second check from curriculum ``common_errors``: True when a known error pattern matches, else undecided."""
    if node is None:
        return None
    lesson = node.payload.get("lesson")
    errors = lesson.get("common_errors", []) if isinstance(lesson, dict) else []
    folded_span = _fold(span)
    for example in errors:
        wrong, right = _fold(example.get("wrong", "")), _fold(example.get("right", ""))
        wrong_words = set(re.findall(r"[\w']+", wrong)) - set(re.findall(r"[\w']+", right))
        if wrong_words and wrong_words <= set(re.findall(r"[\w']+", folded_span)):
            return True
    return None


class UtteranceAssessor:
    def __init__(self, router: LLMRouter, prompts: PromptRegistry, min_confidence: float = 0.85) -> None:
        self._router = router
        self._prompt = prompts.get("utterance_assessor")
        self._check = prompts.get("correction_check")
        self._min_confidence = min_confidence

    async def assess(
        self,
        event: TurnEvent,
        *,
        pack: ExamPack,
        language: Language,
        learner_band: int,
        npc_name: str,
        nodes: dict[str, CurriculumNode],
        trace_id: str | None = None,
    ) -> UtteranceAssessment:
        pack_id = LANGUAGE_PACK[language]
        speaking = next(s for s in pack.sections if s.skill.value == "speaking")
        system, turn = self._prompt.render_split(
            exam=EXAM_NAMES[pack_id],
            language_name=LANGUAGE_NAME[language],
            learner_band=learner_band,
            scale_name=LANGUAGE_SCALE[language],
            npc_name=npc_name,
            last_npc_line=event.npc_context.last_npc_line if event.npc_context else "",
            transcript=event.transcript,
            targets=", ".join(event.targets_active) or "none",
            dimensions=", ".join(speaking.rubric),
            scale_desc=SCALE_DESC[pack_id],
            candidate_nodes=", ".join(sorted(nodes)),
        )
        raw = await self._router.structured(
            "mid",
            self._prompt,
            AssessorOutput,
            self._router.messages("mid", system, turn or "Assess this turn."),
            trace_id=trace_id,
        )
        tags = []
        for tag in raw.errors:
            span = locate(event.transcript, tag.span)
            if span is None or tag.node_key not in nodes:
                continue  # SPEC §10: every tag must cite the exact span and map to a node
            tags.append(
                ErrorTag(
                    node_key=tag.node_key,
                    span=span,
                    correction=tag.correction,
                    explanation=tag.explanation,
                    severity=tag.severity,
                    confidence=tag.confidence,
                )
            )
        tags = [await self._second_check(event.transcript, t, nodes.get(t.node_key), language, trace_id) for t in tags]
        evidence = []
        for item in raw.target_evidence:
            if item.node_key not in event.targets_active:
                continue
            span = locate(event.transcript, item.span) if item.span else None
            if item.span and span is None:
                continue
            evidence.append(
                TargetEvidence(node_key=item.node_key, correct=item.correct, span=span, confidence=item.confidence)
            )
        dimensions = [
            DimensionScore(dimension=d.dimension, score=d.score, confidence=d.confidence, rationale=d.rationale)
            for d in raw.dimensions
            if d.dimension in speaking.rubric
        ]
        return UtteranceAssessment(
            turn_event_id=event.event_id,
            pack=pack_id,
            dimensions=dimensions,
            error_tags=tags,
            target_evidence=evidence,
            band_estimate=raw.band_estimate,
            confidence=raw.confidence,
            model_versions={"assessor": self._prompt.ref, "check": self._check.ref},
        )

    async def _second_check(
        self, transcript: str, tag: ErrorTag, node: CurriculumNode | None, language: Language, trace_id: str | None
    ) -> ErrorTag:
        """SPEC §12.3: only confident tags get the (costlier) independent check; the rest stay evidence-only."""
        if tag.confidence < self._min_confidence:
            return tag
        decided = rule_check(node, tag.span.text)
        if decided is None:
            system = self._check.render(
                language_name=LANGUAGE_NAME[language],
                sentence=transcript,
                span=tag.span.text,
                correction=tag.correction or "",
                explanation=tag.explanation or "",
            )
            verdict = await self._router.structured(
                "mid", self._check, CheckVerdict, [HumanMessage(content=system)], trace_id=trace_id
            )
            decided = verdict.is_error and verdict.confidence >= self._min_confidence
        return tag.model_copy(update={"second_check_agrees": decided})
