"""Typed view of ``config/pedagogy.yaml``."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[5]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Bkt(_Frozen):
    p_init: float
    p_transit: float
    p_slip: float
    p_guess: float
    mastered: float


class Tickets(_Frozen):
    open_after_errors: int
    window_days: int
    close_contexts: int
    close_days: int
    reopen_priority_boost: float
    lesson_after_reopens: int
    max_bands_above: int


class Director(_Frozen):
    ticket_share_min: float
    ticket_share_max: float
    targets_per_scene: int
    scenes_per_day: int
    ticket_ageing_per_day: float


class Steering(_Frozen):
    every_learner_turns: int
    max_hint_chars: int


class Corrections(_Frozen):
    min_confidence: float


class Bands(_Frozen):
    observation_variance: dict[str, float]
    prior_variance: float
    display_interval: float
    crs_confidence: float


class Pedagogy(_Frozen):
    bkt: Bkt
    tickets: Tickets
    director: Director
    steering: Steering
    corrections: Corrections
    bands: Bands


@cache
def load_pedagogy(path: Path = REPO_ROOT / "config" / "pedagogy.yaml") -> Pedagogy:
    return Pedagogy.model_validate(yaml.safe_load(path.read_text()))
