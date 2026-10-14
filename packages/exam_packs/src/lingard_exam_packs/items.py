"""Exam items (original content only, SPEC §23.3) and the bank that serves them."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lingard_contracts.common import Language, PackId, Skill

LOGIT_PER_BAND = 0.75
"""Item difficulty in logits = (band − 7) × LOGIT_PER_BAND, on the CLB/NCLC scale."""


def band_to_logit(band: float) -> float:
    return (band - 7) * LOGIT_PER_BAND


def logit_to_band(theta: float) -> float:
    return 7 + theta / LOGIT_PER_BAND


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    pack: PackId
    language: Language
    skill: Skill
    section: str
    task_type: str
    band: float = Field(ge=1, le=12)
    stimulus: str
    """Reading text, or the audio script for listening items (rendered by TTS, never shown)."""
    question: str
    options: list[str] = Field(min_length=3, max_length=5)
    answer: int
    source: Literal["original", "generated"] = "original"

    @model_validator(mode="after")
    def _valid(self) -> Item:
        if not 0 <= self.answer < len(self.options):
            raise ValueError(f"{self.id}: answer index out of range")
        if len({o.strip().casefold() for o in self.options}) != len(self.options):
            raise ValueError(f"{self.id}: duplicate options")
        if self.stimulus.strip().casefold() in {o.strip().casefold() for o in self.options}:
            raise ValueError(f"{self.id}: an option repeats the stimulus")
        return self

    @property
    def difficulty(self) -> float:
        return band_to_logit(self.band)


class ItemBank:
    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._items: dict[str, Item] = {}
        for item in items:
            self.add(item)

    def add(self, item: Item) -> None:
        if item.id in self._items:
            raise ValueError(f"duplicate item id {item.id}")
        self._items[item.id] = item

    def get(self, item_id: str) -> Item:
        return self._items[item_id]

    def select(self, pack: PackId, skill: Skill, exclude: set[str] | None = None) -> list[Item]:
        return [
            i for i in self._items.values() if i.pack == pack and i.skill == skill and i.id not in (exclude or set())
        ]

    def __len__(self) -> int:
        return len(self._items)

    @classmethod
    def load(cls, content_root: Path) -> ItemBank:
        bank = cls()
        for path in sorted(content_root.glob("packs/*/items/*.yaml")):
            data = yaml.safe_load(path.read_text())
            defaults = data.get("defaults", {})
            for raw in data["items"]:
                bank.add(Item.model_validate({**defaults, **raw}))
        return bank
