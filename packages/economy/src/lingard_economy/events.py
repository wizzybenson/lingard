"""Draw Day, streaks and the friends league (SPEC §18.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DrawOutcome:
    invited: bool
    cutoff: int
    score: int
    margin: int


def draw_day(sim_crs: int, cutoff: int) -> DrawOutcome:
    return DrawOutcome(invited=sim_crs >= cutoff, cutoff=cutoff, score=sim_crs, margin=sim_crs - cutoff)


@dataclass(frozen=True)
class RealDraw:
    """A real Express Entry round whose cutoff Draw Day uses (``content/crs/draws.yaml``)."""

    number: int
    held_on: date
    cutoff: int
    note: str


def load_draws(path: Path) -> list[RealDraw]:
    """The recorded rounds, each with a note naming its source and the date it was checked."""
    data = yaml.safe_load(path.read_text())
    return [
        RealDraw(
            number=d["number"],
            held_on=date.fromisoformat(d["held_on"]),
            cutoff=d["cutoff"],
            note=(
                f"IRCC Express Entry round {d['number']} ({data['category']}, {d['invitations']} invitations). "
                f"Source: {data['source_url']} (as of {data['as_of']})"
            ),
        )
        for d in data["draws"]
    ]


def streak(
    active_days: list[date], today: date, *, covered: frozenset[date] = frozenset(), spare: int = 0
) -> tuple[int, int, list[date]]:
    """(current streak, freezes used, days newly covered by a bought freeze).

    One free freeze per ISO week covers a single missed day; no punishment. ``covered`` are days a bought freeze
    already covered (they stay covered); ``spare`` bought freezes not yet used cover a single missed day each once
    the week's free one is gone. The caller records the newly covered days so a freeze is spent only once.
    """
    days = set(active_days)
    count, freezes_used, cursor = 0, 0, today
    used_weeks: set[tuple[int, int]] = set()
    newly: list[date] = []
    if cursor not in days:
        cursor -= timedelta(days=1)
    while True:
        if cursor in days:
            count += 1
        elif (cursor - timedelta(days=1)) not in days:
            break
        elif cursor in covered:
            freezes_used += 1
        elif (week := cursor.isocalendar()[:2]) not in used_weeks:
            used_weeks.add(week)
            freezes_used += 1
        elif spare > 0:
            spare -= 1
            newly.append(cursor)
            freezes_used += 1
        else:
            break
        cursor -= timedelta(days=1)
    return count, freezes_used, newly


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
