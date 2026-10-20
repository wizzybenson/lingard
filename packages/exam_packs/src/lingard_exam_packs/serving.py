"""Serve items to learners: deterministic per-learner option shuffling and answer mapping."""

from __future__ import annotations

import hashlib
import random
import re

from pydantic import BaseModel

from lingard_exam_packs.items import Item, Response


class ServedItem(BaseModel):
    """What the client receives. Listening items carry an audio ref instead of the script; no answer is ever sent."""

    item_id: str
    question: str
    response: Response = "choice"
    options: list[str] = []
    picks: int = 1
    """How many options to choose (``multi``: "Choose TWO letters")."""
    word_limit: int | None = None
    instructions: str | None = None
    """Set only where the instructions change within a set (a form, then "Choose A, B or C")."""
    text: str | None = None
    audio_ref: str | None = None


class ServedSet(BaseModel):
    """Questions that share one text or recording, served on one screen. The text (reading) or the recording
    (listening) is given once; ``plays`` says how many times the recording may be heard."""

    set_id: str
    part: str | None = None
    instructions: str | None = None
    figure: str | None = None
    text: str | None = None
    audio_ref: str | None = None
    plays: int = 1
    questions: list[ServedItem]


def permutation(item_id: str, learner_seed: str, size: int = 8) -> list[int]:
    digest = hashlib.sha256(f"{learner_seed}:{item_id}".encode()).digest()
    order = list(range(max(8, size)))
    random.Random(digest).shuffle(order)  # noqa: S311
    return order


def _order(item: Item, learner_seed: str) -> list[int]:
    if not item.shuffle:
        return list(range(len(item.options)))
    return [i for i in permutation(item.id, learner_seed, len(item.options)) if i < len(item.options)]


def serve(item: Item, learner_seed: str, audio_ref: str | None = None) -> ServedItem:
    order = _order(item, learner_seed)
    return ServedItem(
        item_id=item.id,
        question=item.question,
        response=item.response,
        options=[item.options[i] for i in order],
        picks=len(item.answer) if isinstance(item.answer, list) else 1,
        word_limit=item.word_limit,
        text=item.stimulus if item.skill.value == "reading" and item.set_id is None else None,
        audio_ref=audio_ref if item.set_id is None else None,
    )


def serve_set(items: list[Item], learner_seed: str, audio_ref: str | None = None) -> ServedSet:
    first = items[0]
    listening = first.skill.value == "listening"
    return ServedSet(
        set_id=first.set_id or first.id,
        part=first.part,
        instructions=first.instructions,
        text=None if listening else first.stimulus,
        audio_ref=audio_ref if listening else None,
        plays=first.plays,
        figure=first.figure,
        questions=[
            serve(item, learner_seed).model_copy(
                update={
                    "text": None,
                    "audio_ref": None,
                    "instructions": item.instructions if n and item.instructions != items[n - 1].instructions else None,
                }
            )
            for n, item in enumerate(items)
        ],
    )


def served_answer(item: Item, learner_seed: str) -> int:
    """Where the right option sits in this learner's order (for practice feedback, never during a mock)."""
    assert isinstance(item.answer, int), f"{item.id} is not a single-choice item"
    return _order(item, learner_seed).index(item.answer)


def is_correct(item: Item, learner_seed: str, chosen_index: int) -> bool:
    return chosen_index == served_answer(item, learner_seed)


_SPACE = re.compile(r"\s+")
_EDGE = re.compile(r"^[^\w£$€]+|[^\w%]+$")


def normalise(text: str) -> str:
    """Case, spacing, curly quotes and edge punctuation never cost a mark; spelling does (as in the real tests)."""
    return _EDGE.sub("", _SPACE.sub(" ", text.replace("’", "'").strip().casefold()))


def words(text: str) -> int:
    """Words towards an IELTS limit: a hyphenated word is one, and a number is not a word ("AND/OR A NUMBER")."""
    return sum(1 for token in normalise(text).split() if not re.fullmatch(r"[\d.,:/£$€%-]+", token))


def check(item: Item, learner_seed: str, value: object) -> bool:
    """Score one answer as served to this learner: an option index, a list of them, or typed words."""
    if item.response == "text":
        if not isinstance(value, str) or not value.strip():
            return False
        if item.word_limit is not None and words(value) > item.word_limit:
            return False
        return normalise(value) in {normalise(a) for a in item.accepted}
    order = _order(item, learner_seed)
    if item.response == "multi":
        if not isinstance(value, list) or not all(isinstance(v, int) and 0 <= v < len(order) for v in value):
            return False
        assert isinstance(item.answer, list)
        return {order[v] for v in value} == set(item.answer)
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value < len(order)
        and order[value] == item.answer
    )
