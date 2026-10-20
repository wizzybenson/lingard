"""Exam pack definitions and official score → CLB/NCLC conversion (SPEC §8.2, §12.2)."""

from __future__ import annotations

import math
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lingard_contracts.common import Language, PackId, Skill


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class TaskDef(_Model):
    id: str
    kind: str
    min_words: int
    suggested_minutes: int
    weight: float = 1
    rubric: list[str]
    variants: list[str] = []
    """The kinds of prompt the exam sets for this task (a formal or personal letter; an opinion or a
    problem–solution essay). Practice prompts are tagged with one, and every variant needs prompts."""


class PartDef(_Model):
    """A speaking part (timed), or a receptive part with its share of the section's questions."""

    id: str
    kind: str | None = None
    minutes: int | list[int] | None = None
    prep_minutes: int | None = None
    items: int | None = None
    task_types: list[str] = Field(default_factory=list)
    """The question types this part uses; the bank must cover each one."""


class SectionDef(_Model):
    id: str
    skill: Skill
    minutes: int | list[int]
    order: int
    items: int | None = None
    tasks: list[TaskDef] = Field(default_factory=list)
    parts: int | list[PartDef] | None = None
    rubric: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _parts_add_up(self) -> SectionDef:
        counted = [p.items for p in self.part_list() if p.items is not None]
        if self.items is not None and counted and sum(counted) != self.items:
            raise ValueError(f"{self.id}: parts hold {sum(counted)} questions, the section {self.items}")
        return self

    @property
    def max_minutes(self) -> int:
        return max(self.minutes) if isinstance(self.minutes, list) else self.minutes

    def part_list(self) -> list[PartDef]:
        return self.parts if isinstance(self.parts, list) else []


class Scale(_Model):
    type: Literal["band", "points"]
    min: float | None = None
    max: float | None = None
    step: float | None = None
    per_module_max: dict[str, int] | None = None


class ExamPack(_Model):
    id: PackId
    name: str
    language: Language
    scale: Scale
    sections: list[SectionDef]
    scale_description: str
    """How the pack's scores are expressed, for prompts (e.g. "IELTS bands 0–9 in half bands")."""
    scene_alignment: dict[Literal["default", "persuasive"], str]
    """Which speaking part a city scene rehearses, by whether its targets are persuasive."""
    source_url: str
    as_of: str

    @model_validator(mode="after")
    def _ordered(self) -> ExamPack:
        orders = [s.order for s in self.sections]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError(f"{self.id}: section order must be 1..n")
        return self

    def section(self, section_id: str) -> SectionDef:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(f"{self.id} has no section {section_id!r}")

    def section_for(self, skill: Skill) -> SectionDef:
        return next(s for s in self.sections if s.skill == skill)

    def ordered_sections(self) -> list[SectionDef]:
        return sorted(self.sections, key=lambda s: s.order)

    def max_score(self, skill: Skill) -> float:
        if self.scale.type == "band":
            return float(self.scale.max or 9)
        assert self.scale.per_module_max is not None
        return float(self.scale.per_module_max[skill.value])

    def min_score(self, skill: Skill) -> float:
        return float(self.scale.min or 0) if self.scale.type == "band" else 0.0


class Conversion(BaseModel):
    """Minimum test score per CLB/NCLC level per skill."""

    model_config = ConfigDict(extra="ignore")

    pack: PackId
    source_url: str
    as_of: str
    levels: dict[int, dict[Skill, float]]

    @cached_property
    def _descending(self) -> list[int]:
        return sorted(self.levels, reverse=True)

    def to_level(self, skill: Skill, score: float) -> int:
        """Highest level whose minimum the score meets; 0 below the lowest tabled level (CLB/NCLC 4)."""
        for level in self._descending:
            if score >= self.levels[level][skill]:
                return level
        return 0

    def mid_score_for(self, skill: Skill, level: int, scale_max: float) -> float:
        """Representative score for a level: midway between its minimum and the next level's minimum."""
        low = self.min_score_for(skill, level)
        higher = sorted(lv for lv in self.levels if lv > level)
        high = self.levels[higher[0]][skill] if higher else scale_max
        return (low + high) / 2

    def min_score_for(self, skill: Skill, level: int) -> float:
        tabled = [lv for lv in self.levels if lv <= level]
        return self.levels[max(tabled)][skill] if tabled else 0.0


def ielts_overall(scores: list[float]) -> float:
    """IELTS overall band: mean of four, rounded to the nearest half band (.25 → .5, .75 → next whole)."""
    if len(scores) != 4:
        raise ValueError("IELTS overall needs four skill bands")
    mean = sum(scores) / 4
    return math.floor(mean * 2 + 0.5) / 2


def _read(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a mapping")
    return data


class PackLibrary:
    """Loads packs and their conversions from ``content/``."""

    def __init__(self, content_root: str | Path) -> None:
        self.root = Path(content_root)
        self._packs: dict[str, ExamPack] = {}
        self._conversions: dict[str, Conversion] = {}

    def pack(self, pack_id: PackId) -> ExamPack:
        if pack_id not in self._packs:
            self._packs[pack_id] = ExamPack.model_validate(_read(self.root / "packs" / pack_id / "pack.yaml"))
        return self._packs[pack_id]

    def conversion(self, pack_id: PackId) -> Conversion:
        if pack_id not in self._conversions:
            raw = _read(self.root / "packs" / pack_id / "pack.yaml")
            rel = raw.get("clb_conversion") or raw.get("nclc_conversion")
            if not isinstance(rel, str):
                raise ValueError(f"{pack_id} has no conversion table")
            table = _read(self.root.parent / rel)
            self._conversions[pack_id] = Conversion.model_validate(table)
        return self._conversions[pack_id]
