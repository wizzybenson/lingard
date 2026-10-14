"""Serve items to learners: deterministic per-learner option shuffling and answer mapping."""

from __future__ import annotations

import hashlib
import random

from pydantic import BaseModel

from lingard_exam_packs.items import Item


class ServedItem(BaseModel):
    """What the client receives. Listening items carry an audio ref instead of the script."""

    item_id: str
    question: str
    options: list[str]
    text: str | None = None
    audio_ref: str | None = None


def permutation(item_id: str, learner_seed: str) -> list[int]:
    digest = hashlib.sha256(f"{learner_seed}:{item_id}".encode()).digest()
    order = list(range(8))
    random.Random(digest).shuffle(order)  # noqa: S311
    return order


def serve(item: Item, learner_seed: str, audio_ref: str | None = None) -> ServedItem:
    order = [i for i in permutation(item.id, learner_seed) if i < len(item.options)]
    return ServedItem(
        item_id=item.id,
        question=item.question,
        options=[item.options[i] for i in order],
        text=item.stimulus if item.skill.value == "reading" else None,
        audio_ref=audio_ref,
    )


def is_correct(item: Item, learner_seed: str, chosen_index: int) -> bool:
    order = [i for i in permutation(item.id, learner_seed) if i < len(item.options)]
    return 0 <= chosen_index < len(order) and order[chosen_index] == item.answer
