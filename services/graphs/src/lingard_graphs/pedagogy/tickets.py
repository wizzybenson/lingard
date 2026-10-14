"""Weakness ticket lifecycle (SPEC §15): open on repeated errors, close after varied success, reopen on recurrence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from lingard_graphs.pedagogy.config import Tickets

Status = Literal["open", "closed", "reopened"]
INTERVENTIONS = ("recast_heavy", "elicit_in_new_setting", "contrast_pair", "lesson")


@dataclass
class Example:
    at: datetime
    text: str
    context: str


@dataclass
class Success:
    at: datetime
    context: str


@dataclass
class Ticket:
    node_key: str
    status: Status = "open"
    severity: float = 0.5
    priority: float = 0.5
    reopen_count: int = 0
    examples: list[Example] = field(default_factory=list)
    successes: list[Success] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.status in ("open", "reopened")


@dataclass
class TicketEvent:
    kind: Literal["opened", "closed", "reopened", "lesson_needed"]
    node_key: str


def should_open(errors: list[datetime], now: datetime, rules: Tickets) -> bool:
    recent = [e for e in errors if now - e <= timedelta(days=rules.window_days)]
    return len(recent) >= rules.open_after_errors


def record_error(
    ticket: Ticket | None,
    node_key: str,
    example: Example,
    severity: float,
    recent_errors: list[datetime],
    rules: Tickets,
) -> tuple[Ticket | None, list[TicketEvent]]:
    events: list[TicketEvent] = []
    if ticket is None:
        if not should_open([*recent_errors, example.at], example.at, rules):
            return None, events
        ticket = Ticket(node_key=node_key, severity=severity, priority=severity, interventions=[INTERVENTIONS[0]])
        ticket.examples.append(example)
        events.append(TicketEvent("opened", node_key))
        return ticket, events
    ticket.examples.append(example)
    ticket.severity = max(ticket.severity, severity)
    if ticket.status == "closed":
        ticket.status = "reopened"
        ticket.reopen_count += 1
        ticket.priority = min(1.0, ticket.priority + rules.reopen_priority_boost)
        ticket.successes = []
        next_intervention = INTERVENTIONS[min(ticket.reopen_count, len(INTERVENTIONS) - 1)]
        ticket.interventions.append(next_intervention)
        events.append(TicketEvent("reopened", node_key))
        if ticket.reopen_count >= rules.lesson_after_reopens:
            events.append(TicketEvent("lesson_needed", node_key))
    return ticket, events


def record_success(ticket: Ticket, success: Success, rules: Tickets) -> list[TicketEvent]:
    if not ticket.active:
        return []
    ticket.successes.append(success)
    contexts = {s.context for s in ticket.successes}
    days = {s.at.date() for s in ticket.successes}
    if len(contexts) >= rules.close_contexts and len(days) >= rules.close_days:
        ticket.status = "closed"
        return [TicketEvent("closed", ticket.node_key)]
    return []
