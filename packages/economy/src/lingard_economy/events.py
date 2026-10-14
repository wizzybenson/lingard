"""Draw Day, streaks and the friends league (SPEC §18.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DrawOutcome:
    invited: bool
    cutoff: int
    score: int
    margin: int


def draw_day(sim_crs: int, cutoff: int) -> DrawOutcome:
    return DrawOutcome(invited=sim_crs >= cutoff, cutoff=cutoff, score=sim_crs, margin=sim_crs - cutoff)


def streak(active_days: list[date], today: date) -> tuple[int, int]:
    """(current streak, freezes used). One free freeze per ISO week covers a single missed day; no punishment."""
    days = set(active_days)
    count, freezes_used, cursor = 0, 0, today
    used_weeks: set[tuple[int, int]] = set()
    if cursor not in days:
        cursor -= timedelta(days=1)
    while True:
        if cursor in days:
            count += 1
        else:
            week = cursor.isocalendar()[:2]
            if week in used_weeks or (cursor - timedelta(days=1)) not in days:
                break
            used_weeks.add(week)
            freezes_used += 1
        cursor -= timedelta(days=1)
    return count, freezes_used


def league(gains: dict[str, int], opted_in: set[str]) -> list[tuple[str, int]]:
    """Weekly ranking by Residency Point gain among opted-in friends only."""
    return sorted(((u, g) for u, g in gains.items() if u in opted_in), key=lambda kv: (-kv[1], kv[0]))


def landing_day_unlocked(mocks: list[dict[str, bool]]) -> bool:
    """Three consecutive mocks at target bands in both packs (most recent last)."""
    run = 0
    for mock in mocks:
        run = run + 1 if mock.get("ielts_gt") and mock.get("tef_canada") else 0
        if run >= 3:
            return True
    return False
