"""Spaced repetition (SPEC §7 ``fsrs_items``) via the reference FSRS scheduler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fsrs import Card, Rating, Scheduler
from fsrs.card import CardDict

_SCHEDULER = Scheduler()


def new_card() -> dict[str, Any]:
    return dict(Card().to_dict())


def review(
    card_data: dict[str, Any], correct: bool, *, hesitant: bool = False, now: datetime | None = None
) -> dict[str, Any]:
    """Grade from evidence: wrong → Again, correct-but-hesitant → Hard, correct → Good."""
    rating = Rating.Again if not correct else (Rating.Hard if hesitant else Rating.Good)
    card = Card.from_dict(cast(CardDict, card_data))
    updated, _ = _SCHEDULER.review_card(card, rating, review_datetime=now or datetime.now(UTC))
    return dict(updated.to_dict())


def due_at(card_data: dict[str, Any]) -> datetime:
    return Card.from_dict(cast(CardDict, card_data)).due
