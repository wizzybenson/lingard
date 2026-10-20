"""The learner's streak with the freezes they bought (decision 0023).

A bought freeze is spent the first time it covers a missed day, and that day is written to the ledger (zero coins,
``freeze_used``) so the same freeze is never spent twice and the day stays covered.
"""

from __future__ import annotations

import uuid
from datetime import date

from lingard_economy.events import streak
from lingard_economy.rewards import LedgerEntry
from lingard_graphs.store import LearnerStore

BOUGHT = "shop:streak_freeze"
USED = "freeze_used"


async def learner_streak(store: LearnerStore, user_id: uuid.UUID, today: date) -> tuple[int, int]:
    """(current streak, spare freezes left)."""
    bought = len(await store.ledger_refs(user_id, BOUGHT))
    covered = frozenset(date.fromisoformat(d) for d in await store.ledger_refs(user_id, USED))
    current, _, newly = streak(
        await store.active_days(user_id), today, covered=covered, spare=max(0, bought - len(covered))
    )
    if newly:
        await store.apply_ledger(
            user_id, [LedgerEntry("coins", 0, USED, d.isoformat(), f"freeze:{d.isoformat()}") for d in newly]
        )
    return current, max(0, bought - len(covered) - len(newly))
