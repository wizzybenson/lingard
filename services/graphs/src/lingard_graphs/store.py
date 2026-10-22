"""Persistence seam for the graphs: ``MemoryStore`` for tests and synthetic learners, ``SqlStore`` for prod."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from lingard_contracts.assessment import UtteranceAssessment, WritingAssessment
from lingard_contracts.events import TurnEvent
from lingard_contracts.planning import DayPlan
from lingard_contracts.scene import SceneContract
from lingard_economy.rewards import LedgerEntry
from lingard_graphs.pedagogy.bands import BandPosterior
from lingard_graphs.pedagogy.mastery import MasteryState
from lingard_graphs.pedagogy.tickets import Ticket

ERROR_WINDOW = timedelta(days=30)
"""How far back error timestamps are kept for ticket-opening decisions."""


@dataclass
class LearnerProfileView:
    user_id: uuid.UUID
    display_name: str
    l1: str
    intensity_cap: str
    target_bands: dict[str, dict[str, int]]
    crs_inputs: dict[str, Any]
    language_bands: dict[str, int]
    """Current working CLB/NCLC band per language, derived from the posteriors."""
    ui_locale: str | None = None
    """The interface language the learner chose (en, fr, ar)."""

    @property
    def explain_in(self) -> str:
        """The language explanations are written in: the interface's, else the learner's first language."""
        return self.ui_locale or self.l1


@dataclass
class SceneRecord:
    scene_id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    contract: SceneContract
    status: str = "planned"
    outcome: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


class LearnerStore(Protocol):
    async def profile(self, user_id: uuid.UUID) -> LearnerProfileView: ...

    async def scene(self, scene_id: uuid.UUID) -> SceneRecord | None: ...

    async def save_scene(self, record: SceneRecord) -> None: ...

    async def open_exam_session(self, session_id: uuid.UUID, user_id: uuid.UUID, city: str) -> None:
        """The session that holds a mock's live speaking scenes (idempotent: a resumed graph calls it again)."""
        ...

    async def scenes_for_session(self, session_id: uuid.UUID) -> list[SceneRecord]: ...

    async def turns(self, scene_id: uuid.UUID) -> list[TurnEvent]: ...

    async def save_turn(self, event: TurnEvent) -> bool:
        """Idempotent on ``event_id``; returns False when already stored."""
        ...

    async def assessment_exists(self, event_id: uuid.UUID) -> bool: ...

    async def save_assessment(self, user_id: uuid.UUID, assessment: UtteranceAssessment) -> None: ...

    async def assessments_for_scene(self, scene_id: uuid.UUID) -> list[UtteranceAssessment]: ...

    async def save_writing(
        self, user_id: uuid.UUID, prompt: str, text: str, assessment: WritingAssessment
    ) -> uuid.UUID: ...

    async def mastery(self, user_id: uuid.UUID, keys: list[str]) -> dict[str, MasteryState]: ...

    async def save_mastery(self, user_id: uuid.UUID, states: list[MasteryState], at: datetime) -> None: ...

    async def all_mastery(self, user_id: uuid.UUID) -> dict[str, MasteryState]: ...

    async def tickets(self, user_id: uuid.UUID, active_only: bool = True) -> dict[str, Ticket]: ...

    async def save_ticket(self, user_id: uuid.UUID, ticket: Ticket) -> None: ...

    async def recent_errors(self, user_id: uuid.UUID, node_key: str) -> list[datetime]: ...

    async def record_error_time(self, user_id: uuid.UUID, node_key: str, at: datetime) -> None: ...

    async def posteriors(self, user_id: uuid.UUID) -> dict[tuple[str, str], BandPosterior]: ...

    async def save_posterior(self, user_id: uuid.UUID, pack: str, skill: str, posterior: BandPosterior) -> None: ...

    async def fsrs(self, user_id: uuid.UUID) -> dict[str, dict[str, Any]]: ...

    async def save_fsrs(self, user_id: uuid.UUID, item_key: str, card: dict[str, Any]) -> None: ...

    async def save_day_plan(
        self, plan: DayPlan, session_id: uuid.UUID | None = None, *, complete: bool = True
    ) -> uuid.UUID:
        """Store the plan on ``session_id`` (marking it ready) or on a new session; returns the session id.
        ``complete=False``: the first scene is playable while the rest of the day is still being compiled."""
        ...

    async def fail_day_plan(self, session_id: uuid.UUID, reason: str) -> None:
        """Mark a session whose planning gave up, so the client stops waiting and can say why."""
        ...

    async def world_state(self, user_id: uuid.UUID, city: str) -> dict[str, Any]: ...

    async def save_world_state(self, user_id: uuid.UUID, city: str, state: dict[str, Any]) -> None: ...

    async def relationship(self, user_id: uuid.UUID, npc_key: str) -> tuple[float, str]: ...

    async def save_relationship(self, user_id: uuid.UUID, npc_key: str, affinity: float, summary: str) -> None: ...

    async def save_notebook(self, user_id: uuid.UUID, session_id: uuid.UUID, notebook: dict[str, Any]) -> None: ...

    async def save_lesson(self, user_id: uuid.UUID, node_key: str, lesson: dict[str, Any]) -> uuid.UUID: ...

    async def apply_ledger(self, user_id: uuid.UUID, entries: list[LedgerEntry]) -> int:
        """Append idempotently (``idempotency_key``) and update the wallet; returns how many were new."""
        ...

    async def ledger_refs(self, user_id: uuid.UUID, reason: str) -> list[str]:
        """The ``ref_id`` of each of the learner's ledger entries with this reason, oldest first."""
        ...

    async def wallet(self, user_id: uuid.UUID) -> tuple[int, int]:
        """(coins, stars_total)."""
        ...

    async def save_crs_snapshot(self, user_id: uuid.UUID, value: int, breakdown: dict[str, Any]) -> None: ...

    async def latest_crs(self, user_id: uuid.UUID) -> int | None: ...

    async def save_language_band(self, user_id: uuid.UUID, language: str, band: int) -> None: ...

    async def active_days(self, user_id: uuid.UUID) -> list[date]: ...

    async def days_lived(self, user_id: uuid.UUID, city: str) -> int:
        """Story days finished in ``city``: progress through the story, independent of the calendar."""
        ...

    async def mark_active(self, user_id: uuid.UUID, day: date, kind: str | None = None) -> None:
        """Any practice (reviews, a lesson, writing, the Accent Studio) keeps the streak, not only live scenes.
        ``kind`` ("review", "lesson", "sounds", "writing") is recorded for that day: it ticks that stop of today's path
        and tells the learning coach what the learner followed."""
        ...

    async def save_mock(self, user_id: uuid.UUID, record: dict[str, Any]) -> uuid.UUID: ...

    async def mocks(self, user_id: uuid.UUID) -> list[dict[str, Any]]: ...


@dataclass
class MemoryStore:
    """Complete in-memory implementation (tests, evals, synthetic learners)."""

    profiles: dict[uuid.UUID, LearnerProfileView] = field(default_factory=dict)
    scenes: dict[uuid.UUID, SceneRecord] = field(default_factory=dict)
    turn_log: dict[uuid.UUID, list[TurnEvent]] = field(default_factory=lambda: defaultdict(list))
    seen_events: set[uuid.UUID] = field(default_factory=set)
    assessments: dict[uuid.UUID, tuple[uuid.UUID, UtteranceAssessment]] = field(default_factory=dict)
    writings: dict[uuid.UUID, tuple[uuid.UUID, str, str, WritingAssessment]] = field(default_factory=dict)
    mastery_by_user: dict[uuid.UUID, dict[str, MasteryState]] = field(default_factory=lambda: defaultdict(dict))
    tickets_by_user: dict[uuid.UUID, dict[str, Ticket]] = field(default_factory=lambda: defaultdict(dict))
    error_times: dict[tuple[uuid.UUID, str], list[datetime]] = field(default_factory=lambda: defaultdict(list))
    posterior_by_user: dict[uuid.UUID, dict[tuple[str, str], BandPosterior]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    fsrs_by_user: dict[uuid.UUID, dict[str, dict[str, Any]]] = field(default_factory=lambda: defaultdict(dict))
    plans: dict[uuid.UUID, DayPlan] = field(default_factory=dict)
    failed_plans: dict[uuid.UUID, str] = field(default_factory=dict)
    incomplete_plans: set[uuid.UUID] = field(default_factory=set)
    lived: dict[tuple[uuid.UUID, str], int] = field(default_factory=dict)
    worlds: dict[tuple[uuid.UUID, str], dict[str, Any]] = field(default_factory=dict)
    relationships: dict[tuple[uuid.UUID, str], tuple[float, str]] = field(default_factory=dict)
    notebooks: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = field(default_factory=dict)
    lessons: dict[uuid.UUID, tuple[uuid.UUID, str, dict[str, Any]]] = field(default_factory=dict)
    ledgers: dict[uuid.UUID, list[LedgerEntry]] = field(default_factory=lambda: defaultdict(list))
    crs: dict[uuid.UUID, list[tuple[int, dict[str, Any]]]] = field(default_factory=lambda: defaultdict(list))
    days: dict[uuid.UUID, set[date]] = field(default_factory=lambda: defaultdict(set))
    mock_records: dict[uuid.UUID, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    exam_sessions: dict[uuid.UUID, tuple[uuid.UUID, str]] = field(default_factory=dict)

    async def profile(self, user_id: uuid.UUID) -> LearnerProfileView:
        return self.profiles[user_id]

    async def scene(self, scene_id: uuid.UUID) -> SceneRecord | None:
        return self.scenes.get(scene_id)

    async def save_scene(self, record: SceneRecord) -> None:
        self.scenes[record.scene_id] = record

    async def open_exam_session(self, session_id: uuid.UUID, user_id: uuid.UUID, city: str) -> None:
        self.exam_sessions.setdefault(session_id, (user_id, city))

    async def scenes_for_session(self, session_id: uuid.UUID) -> list[SceneRecord]:
        return [s for s in self.scenes.values() if s.session_id == session_id]

    async def turns(self, scene_id: uuid.UUID) -> list[TurnEvent]:
        return sorted(self.turn_log[scene_id], key=lambda t: t.turn_index)

    async def save_turn(self, event: TurnEvent) -> bool:
        if event.event_id in self.seen_events:
            return False
        self.seen_events.add(event.event_id)
        self.turn_log[event.scene_id].append(event)
        return True

    async def assessment_exists(self, event_id: uuid.UUID) -> bool:
        return event_id in self.assessments

    async def save_assessment(self, user_id: uuid.UUID, assessment: UtteranceAssessment) -> None:
        self.assessments[assessment.turn_event_id] = (user_id, assessment)

    async def assessments_for_scene(self, scene_id: uuid.UUID) -> list[UtteranceAssessment]:
        event_ids = {t.event_id for t in self.turn_log[scene_id]}
        return [a for eid, (_, a) in self.assessments.items() if eid in event_ids]

    async def save_writing(
        self, user_id: uuid.UUID, prompt: str, text: str, assessment: WritingAssessment
    ) -> uuid.UUID:
        submission_id = uuid.uuid4()
        self.writings[submission_id] = (user_id, prompt, text, assessment)
        return submission_id

    async def mastery(self, user_id: uuid.UUID, keys: list[str]) -> dict[str, MasteryState]:
        return {k: v for k, v in self.mastery_by_user[user_id].items() if k in keys}

    async def save_mastery(self, user_id: uuid.UUID, states: list[MasteryState], at: datetime) -> None:
        for state in states:
            self.mastery_by_user[user_id][state.node_key] = state

    async def all_mastery(self, user_id: uuid.UUID) -> dict[str, MasteryState]:
        return dict(self.mastery_by_user[user_id])

    async def tickets(self, user_id: uuid.UUID, active_only: bool = True) -> dict[str, Ticket]:
        return {k: t for k, t in self.tickets_by_user[user_id].items() if t.active or not active_only}

    async def save_ticket(self, user_id: uuid.UUID, ticket: Ticket) -> None:
        self.tickets_by_user[user_id][ticket.node_key] = ticket

    async def recent_errors(self, user_id: uuid.UUID, node_key: str) -> list[datetime]:
        times = self.error_times[(user_id, node_key)]
        if not times:
            return []
        cutoff = max(times) - ERROR_WINDOW
        return [t for t in times if t > cutoff]

    async def record_error_time(self, user_id: uuid.UUID, node_key: str, at: datetime) -> None:
        self.error_times[(user_id, node_key)].append(at)

    async def posteriors(self, user_id: uuid.UUID) -> dict[tuple[str, str], BandPosterior]:
        return dict(self.posterior_by_user[user_id])

    async def save_posterior(self, user_id: uuid.UUID, pack: str, skill: str, posterior: BandPosterior) -> None:
        self.posterior_by_user[user_id][(pack, skill)] = posterior

    async def fsrs(self, user_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        return dict(self.fsrs_by_user[user_id])

    async def save_fsrs(self, user_id: uuid.UUID, item_key: str, card: dict[str, Any]) -> None:
        self.fsrs_by_user[user_id][item_key] = card

    async def save_day_plan(
        self, plan: DayPlan, session_id: uuid.UUID | None = None, *, complete: bool = True
    ) -> uuid.UUID:
        plan_id = session_id or uuid.uuid4()
        self.plans[plan_id] = plan
        if complete:
            self.incomplete_plans.discard(plan_id)
        else:
            self.incomplete_plans.add(plan_id)
        return plan_id

    async def fail_day_plan(self, session_id: uuid.UUID, reason: str) -> None:
        self.failed_plans[session_id] = reason

    async def world_state(self, user_id: uuid.UUID, city: str) -> dict[str, Any]:
        return dict(self.worlds.get((user_id, city), {"story_flags": {}, "district_unlocks": [], "inventory": []}))

    async def save_world_state(self, user_id: uuid.UUID, city: str, state: dict[str, Any]) -> None:
        self.worlds[(user_id, city)] = state

    async def relationship(self, user_id: uuid.UUID, npc_key: str) -> tuple[float, str]:
        return self.relationships.get((user_id, npc_key), (0.0, ""))

    async def save_relationship(self, user_id: uuid.UUID, npc_key: str, affinity: float, summary: str) -> None:
        self.relationships[(user_id, npc_key)] = (affinity, summary)

    async def save_notebook(self, user_id: uuid.UUID, session_id: uuid.UUID, notebook: dict[str, Any]) -> None:
        self.notebooks[(user_id, session_id)] = notebook

    async def save_lesson(self, user_id: uuid.UUID, node_key: str, lesson: dict[str, Any]) -> uuid.UUID:
        lesson_id = uuid.uuid4()
        self.lessons[lesson_id] = (user_id, node_key, lesson)
        return lesson_id

    async def apply_ledger(self, user_id: uuid.UUID, entries: list[LedgerEntry]) -> int:
        seen = {e.idempotency_key for e in self.ledgers[user_id]}
        new = [e for e in entries if e.idempotency_key not in seen]
        self.ledgers[user_id].extend(new)
        return len(new)

    async def ledger_refs(self, user_id: uuid.UUID, reason: str) -> list[str]:
        return [e.ref_id for e in self.ledgers[user_id] if e.reason == reason]

    async def wallet(self, user_id: uuid.UUID) -> tuple[int, int]:
        entries = self.ledgers[user_id]
        return (
            sum(e.delta for e in entries if e.currency == "coins"),
            sum(e.delta for e in entries if e.currency == "stars"),
        )

    async def save_crs_snapshot(self, user_id: uuid.UUID, value: int, breakdown: dict[str, Any]) -> None:
        self.crs[user_id].append((value, breakdown))

    async def latest_crs(self, user_id: uuid.UUID) -> int | None:
        return self.crs[user_id][-1][0] if self.crs[user_id] else None

    async def save_language_band(self, user_id: uuid.UUID, language: str, band: int) -> None:
        self.profiles[user_id].language_bands[language] = band

    async def active_days(self, user_id: uuid.UUID) -> list[date]:
        return sorted(self.days[user_id])

    async def days_lived(self, user_id: uuid.UUID, city: str) -> int:
        return self.lived.get((user_id, city), 0)

    async def mark_active(self, user_id: uuid.UUID, day: date, kind: str | None = None) -> None:
        self.days[user_id].add(day)

    async def save_mock(self, user_id: uuid.UUID, record: dict[str, Any]) -> uuid.UUID:
        mock_id = uuid.uuid4()
        self.mock_records[user_id].append({**record, "id": str(mock_id)})
        return mock_id

    async def mocks(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        return list(self.mock_records[user_id])
