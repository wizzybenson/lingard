"""Assessment outputs (SPEC §10, §12)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from lingard_contracts.common import NodeKey, PackId, Skill, Strict

CORRECTION_CONFIDENCE = 0.85
"""SPEC §12.3: minimum tag confidence before a correction may be shown."""


class Span(Strict):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def _ordered(self) -> Span:
        if self.end < self.start:
            raise ValueError("span end before start")
        return self


class ErrorTag(Strict):
    """A suspected error, mapped to a curriculum node and citing the exact span."""

    node_key: NodeKey
    span: Span
    correction: str | None = None
    explanation: str | None = None
    severity: Literal["minor", "major", "intelligibility"] = "minor"
    confidence: float = Field(ge=0, le=1)
    second_check_agrees: bool | None = None

    @property
    def showable(self) -> bool:
        """Only high-confidence, independently confirmed tags may be shown as corrections."""
        return self.confidence >= CORRECTION_CONFIDENCE and self.second_check_agrees is True


class DimensionScore(Strict):
    dimension: str
    score: float
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


class TargetEvidence(Strict):
    node_key: NodeKey
    correct: bool
    span: Span | None = None
    confidence: float = Field(ge=0, le=1)


class UtteranceAssessment(Strict):
    turn_event_id: UUID
    pack: PackId
    dimensions: list[DimensionScore]
    error_tags: list[ErrorTag] = Field(default_factory=list)
    target_evidence: list[TargetEvidence] = Field(default_factory=list)
    band_estimate: float | None = None
    confidence: float = Field(ge=0, le=1)
    model_versions: dict[str, str] = Field(default_factory=dict)


class WritingAssessment(Strict):
    pack: PackId
    task_type: str
    word_count: int
    dimensions: list[DimensionScore]
    band_or_points: float
    rewrite: str
    error_tags: list[ErrorTag] = Field(default_factory=list)
    samples: int = 3
    model_versions: dict[str, str] = Field(default_factory=dict)


class BandEstimate(Strict):
    """Posterior summary. Never displayed without its interval (SPEC §12.2)."""

    pack: PackId
    skill: Skill
    mean: float
    sd: float = Field(gt=0)
    low80: float
    high80: float
    clb_nclc_low: int | None = None
    clb_nclc_mean: int | None = None
    clb_nclc_high: int | None = None
    observations: int = 0


class SteeringHint(Strict):
    """At most one every 4 learner turns; never contains a correction (SPEC §10)."""

    text: str = Field(max_length=160)
    after_turn: int
