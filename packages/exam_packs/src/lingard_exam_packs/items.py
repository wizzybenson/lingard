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


Response = Literal["choice", "multi", "text"]


class Item(BaseModel):
    """One scored question. Questions that share a text or recording carry the same ``set_id`` and ``stimulus``
    and are served together, as in the real tests (an IELTS Part 1 form, a TEF radio report with several questions).

    ``response`` is how the learner answers: one option (``choice``), several options (``multi``: "choose TWO"),
    or a few words typed from the text or recording (``text``: completion and short-answer tasks).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    pack: PackId
    language: Language
    skill: Skill
    section: str
    part: str | None = None
    """The pack blueprint part this question belongs to (IELTS Listening part2, a TEF reading activity)."""
    task_type: str
    band: float = Field(ge=1, le=12)
    stimulus: str
    """Reading text, or the audio script for listening items (rendered by TTS, never shown)."""
    set_id: str | None = None
    instructions: str | None = None
    """What the official paper prints above the questions, e.g. "Write NO MORE THAN TWO WORDS AND/OR A NUMBER"."""
    figure: str | None = None
    """A plan or chart drawn in monospace text (map labelling, chart reading), shown with the questions."""
    question: str
    response: Response = "choice"
    options: list[str] = Field(default_factory=list, max_length=12)
    answer: int | list[int] | None = None
    accepted: list[str] = Field(default_factory=list)
    """Text answers: every acceptable spelling of the right answer."""
    word_limit: int | None = Field(default=None, ge=1, le=5)
    shuffle: bool = True
    """False when the option order carries meaning: True/False/Not Given, lettered headings, map labels."""
    plays: int = Field(default=1, ge=1, le=2)
    """How many times the recording may be heard (IELTS: once; TEF interviews: twice)."""
    source: Literal["original", "generated"] = "original"

    @model_validator(mode="after")
    def _valid(self) -> Item:
        if self.response == "text":
            if not self.accepted or self.options or self.answer is not None:
                raise ValueError(f"{self.id}: a text answer needs accepted answers and no options")
            return self
        if not 2 <= len(self.options) <= 12:
            raise ValueError(f"{self.id}: needs 2–12 options")
        if len({o.strip().casefold() for o in self.options}) != len(self.options):
            raise ValueError(f"{self.id}: duplicate options")
        if self.stimulus.strip().casefold() in {o.strip().casefold() for o in self.options}:
            raise ValueError(f"{self.id}: an option repeats the stimulus")
        keys = self.answer if isinstance(self.answer, list) else [self.answer]
        if self.response == "choice" and not isinstance(self.answer, int):
            raise ValueError(f"{self.id}: a choice item needs one answer index")
        if self.response == "multi" and not (isinstance(self.answer, list) and len(set(self.answer)) >= 2):
            raise ValueError(f"{self.id}: a multi item needs two or more answer indexes")
        if not all(isinstance(k, int) and 0 <= k < len(self.options) for k in keys):
            raise ValueError(f"{self.id}: answer index out of range")
        return self

    @property
    def difficulty(self) -> float:
        return band_to_logit(self.band)

    @property
    def standalone(self) -> bool:
        """A single multiple-choice question with its own text: what adaptive placement and Glance can serve."""
        return self.set_id is None and self.response == "choice"


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

    def select(
        self, pack: PackId, skill: Skill, exclude: set[str] | None = None, *, standalone: bool = False
    ) -> list[Item]:
        return [
            i
            for i in self._items.values()
            if i.pack == pack
            and i.skill == skill
            and i.id not in (exclude or set())
            and (i.standalone or not standalone)
        ]

    def sets(self, pack: PackId, section: str) -> dict[str, list[Item]]:
        """A section's questions grouped as they are served: by shared text, or one per standalone question."""
        groups: dict[str, list[Item]] = {}
        for item in self._items.values():
            if item.pack == pack and item.section == section:
                groups.setdefault(item.set_id or item.id, []).append(item)
        return groups

    def __len__(self) -> int:
        return len(self._items)

    @classmethod
    def load(cls, content_root: Path) -> ItemBank:
        bank = cls()
        for path in sorted(content_root.glob("packs/*/items/*.yaml")):
            data = yaml.safe_load(path.read_text())
            defaults = data.get("defaults", {})
            for raw in data.get("items", []):
                bank.add(Item.model_validate({**defaults, **raw}))
            for raw_set in data.get("sets", []):
                for item in expand_set(defaults, raw_set):
                    bank.add(item)
        return bank


def expand_set(defaults: dict[str, object], raw_set: dict[str, object]) -> list[Item]:
    """A set in the YAML: shared fields once (id, stimulus, instructions, part, band...), then its questions.
    Question ids are the set id plus the question's number; a question may override any shared field."""
    shared = {k: v for k, v in raw_set.items() if k not in ("id", "questions")}
    questions = raw_set["questions"]
    assert isinstance(questions, list)
    items = []
    for n, q in enumerate(questions, start=1):
        merged = {**defaults, **shared, "id": f"{raw_set['id']}-q{n}", "set_id": raw_set["id"], **q}
        if merged.get("response") == "text" and "options" not in q:
            merged.pop("options", None)  # a typed answer never carries the set's option list
        items.append(Item.model_validate(merged))
    return items
