"""Director target selection (SPEC §10, §15.3): 40–60% from open tickets, interleaved, never in the failed setting."""

from __future__ import annotations

import random
from dataclasses import dataclass

from lingard_graphs.pedagogy.config import Director


@dataclass(frozen=True)
class Candidate:
    node_key: str
    priority: float
    failed_settings: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Slot:
    setting: str
    targets: tuple[str, ...]
    ticket_targets: tuple[str, ...]


def plan_targets(
    tickets: list[Candidate],
    fresh: list[Candidate],
    settings: list[str],
    rules: Director,
    rng: random.Random | None = None,
) -> list[Slot]:
    """Distribute targets over the day's settings. Ticket share is clamped into [min, max] when supply allows."""
    rnd = rng or random.Random(0)  # noqa: S311  (deterministic shuffling, not security)
    total = rules.targets_per_scene * len(settings)
    want_tickets = round(total * (rules.ticket_share_min + rules.ticket_share_max) / 2)
    want_tickets = max(round(total * rules.ticket_share_min), min(want_tickets, round(total * rules.ticket_share_max)))
    ticket_pool = sorted(tickets, key=lambda c: c.priority, reverse=True)
    fresh_pool = sorted(fresh, key=lambda c: c.priority, reverse=True)

    slots: list[list[Candidate]] = [[] for _ in settings]
    ticket_count = 0
    # Interleave: round-robin over settings so tickets spread across scenes.
    index = 0
    attempts = 0
    while ticket_pool and ticket_count < want_tickets and attempts < total * 4:
        attempts += 1
        slot = index % len(settings)
        index += 1
        if len(slots[slot]) >= rules.targets_per_scene:
            continue
        pick = next((c for c in ticket_pool if settings[slot] not in c.failed_settings), None)
        if pick is None:
            continue
        ticket_pool.remove(pick)
        slots[slot].append(pick)
        ticket_count += 1
    for slot_targets in slots:
        while len(slot_targets) < rules.targets_per_scene and fresh_pool:
            slot_targets.append(fresh_pool.pop(0))
    for slot_targets in slots:
        rnd.shuffle(slot_targets)
    ticket_keys = {c.node_key for c in tickets}
    return [
        Slot(
            setting=settings[i],
            targets=tuple(c.node_key for c in chosen),
            ticket_targets=tuple(c.node_key for c in chosen if c.node_key in ticket_keys),
        )
        for i, chosen in enumerate(slots)
        if chosen
    ]
