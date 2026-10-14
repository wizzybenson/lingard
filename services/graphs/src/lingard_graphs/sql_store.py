"""``LearnerStore`` over the shared Postgres schema (``lingard_db.models``). Every query is scoped to its user."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lingard_contracts.assessment import UtteranceAssessment, WritingAssessment
from lingard_contracts.events import TurnEvent
from lingard_contracts.planning import DayPlan
from lingard_contracts.scene import SceneContract
from lingard_db import models as m
from lingard_economy.rewards import LedgerEntry
from lingard_graphs.pedagogy.bands import BandPosterior
from lingard_graphs.pedagogy.mastery import MasteryState
from lingard_graphs.pedagogy.review import due_at
from lingard_graphs.pedagogy.tickets import Example, Success, Ticket
from lingard_graphs.store import ERROR_WINDOW, LearnerProfileView, SceneRecord


def _ticket(row: m.WeaknessTicket) -> Ticket:
    return Ticket(
        node_key=row.node_key,
        status=row.status,  # type: ignore[arg-type]
        severity=row.severity,
        priority=row.priority,
        reopen_count=row.reopen_count,
        examples=[Example(datetime.fromisoformat(e["at"]), e["text"], e["context"]) for e in row.examples],
        successes=[Success(datetime.fromisoformat(s["at"]), s["context"]) for s in row.success_contexts],
        interventions=[i["kind"] for i in row.interventions],
    )


class SqlStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _tenant(self, db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
        return (await db.get_one(m.User, user_id)).tenant_id

    async def profile(self, user_id: uuid.UUID) -> LearnerProfileView:
        async with self._sessions() as db:
            user = await db.get_one(m.User, user_id)
            profile = (
                await db.execute(select(m.LearnerProfile).where(m.LearnerProfile.user_id == user_id))
            ).scalar_one()
            bands = dict(profile.settings.get("language_bands", {}))
        return LearnerProfileView(
            user_id=user_id,
            display_name=user.display_name,
            l1=profile.l1,
            intensity_cap=profile.intensity_cap,
            target_bands=profile.target_bands,
            crs_inputs=profile.crs_inputs,
            language_bands=bands,
        )

    async def scene(self, scene_id: uuid.UUID) -> SceneRecord | None:
        async with self._sessions() as db:
            row = await db.get(m.Scene, scene_id)
        if row is None:
            return None
        return SceneRecord(
            scene_id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            contract=SceneContract.model_validate(row.contract),
            status=row.status,
            outcome=row.outcome,
            created_at=row.created_at,
        )

    async def save_scene(self, record: SceneRecord) -> None:
        async with self._sessions() as db, db.begin():
            row = await db.get(m.Scene, record.scene_id)
            if row is None:
                db.add(
                    m.Scene(
                        id=record.scene_id,
                        tenant_id=await self._tenant(db, record.user_id),
                        user_id=record.user_id,
                        session_id=record.session_id,
                        contract=record.contract.model_dump(mode="json"),
                        status=record.status,
                        outcome=record.outcome,
                    )
                )
            else:
                row.contract, row.status, row.outcome = (
                    record.contract.model_dump(mode="json"),
                    record.status,
                    record.outcome,
                )

    async def scenes_for_session(self, session_id: uuid.UUID) -> list[SceneRecord]:
        async with self._sessions() as db:
            ids = (await db.execute(select(m.Scene.id).where(m.Scene.session_id == session_id))).scalars().all()
        return [r for r in [await self.scene(i) for i in ids] if r is not None]

    async def turns(self, scene_id: uuid.UUID) -> list[TurnEvent]:
        async with self._sessions() as db:
            rows = (
                await db.execute(select(m.Turn).where(m.Turn.scene_id == scene_id).order_by(m.Turn.index))
            ).scalars()
            return [TurnEvent.model_validate(r.timings["event"]) for r in rows]

    async def save_turn(self, event: TurnEvent) -> bool:
        async with self._sessions() as db, db.begin():
            statement = (
                insert(m.Turn)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=await self._tenant(db, event.user_id),
                    user_id=event.user_id,
                    scene_id=event.scene_id,
                    event_id=event.event_id,
                    index=event.turn_index,
                    speaker=event.speaker,
                    transcript=event.transcript,
                    audio_ref=event.audio_ref,
                    timings={"event": event.model_dump(mode="json")},
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(m.Turn.id)
            )
            return (await db.execute(statement)).first() is not None

    async def assessment_exists(self, event_id: uuid.UUID) -> bool:
        async with self._sessions() as db:
            return (
                await db.execute(select(m.Assessment.id).where(m.Assessment.event_id == event_id))
            ).first() is not None

    async def save_assessment(self, user_id: uuid.UUID, assessment: UtteranceAssessment) -> None:
        async with self._sessions() as db, db.begin():
            turn = (
                await db.execute(select(m.Turn).where(m.Turn.event_id == assessment.turn_event_id))
            ).scalar_one_or_none()
            await db.execute(
                insert(m.Assessment)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    turn_id=turn.id if turn else None,
                    event_id=assessment.turn_event_id,
                    pack=assessment.pack,
                    dimension_scores=[d.model_dump() for d in assessment.dimensions],
                    band_estimate=assessment.band_estimate,
                    confidence=assessment.confidence,
                    error_tags=[t.model_dump() for t in assessment.error_tags],
                    model_versions={
                        **assessment.model_versions,
                        "evidence": [e.model_dump(mode="json") for e in assessment.target_evidence],
                    },
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
            )

    async def assessments_for_scene(self, scene_id: uuid.UUID) -> list[UtteranceAssessment]:
        async with self._sessions() as db:
            rows = (
                await db.execute(
                    select(m.Assessment)
                    .join(m.Turn, m.Assessment.turn_id == m.Turn.id)
                    .where(m.Turn.scene_id == scene_id)
                )
            ).scalars()
            out = []
            for row in rows:
                versions = dict(row.model_versions)
                evidence = versions.pop("evidence", [])
                out.append(
                    UtteranceAssessment.model_validate(
                        {
                            "turn_event_id": row.event_id,
                            "pack": row.pack,
                            "dimensions": row.dimension_scores,
                            "error_tags": row.error_tags,
                            "target_evidence": evidence,
                            "band_estimate": row.band_estimate,
                            "confidence": row.confidence,
                            "model_versions": versions,
                        }
                    )
                )
            return out

    async def save_writing(
        self, user_id: uuid.UUID, prompt: str, text: str, assessment: WritingAssessment
    ) -> uuid.UUID:
        async with self._sessions() as db, db.begin():
            row = m.WritingSubmission(
                tenant_id=await self._tenant(db, user_id),
                user_id=user_id,
                pack=assessment.pack,
                task_type=assessment.task_type,
                prompt=prompt,
                text=text,
                word_count=assessment.word_count,
                scores=assessment.model_dump(mode="json"),
                rewrite=assessment.rewrite,
            )
            db.add(row)
            await db.flush()
            return row.id

    async def mastery(self, user_id: uuid.UUID, keys: list[str]) -> dict[str, MasteryState]:
        async with self._sessions() as db:
            rows = (
                await db.execute(select(m.Mastery).where(m.Mastery.user_id == user_id, m.Mastery.node_key.in_(keys)))
            ).scalars()
            return {r.node_key: MasteryState(r.node_key, r.p_mastery, r.evidence_count, list(r.contexts)) for r in rows}

    async def all_mastery(self, user_id: uuid.UUID) -> dict[str, MasteryState]:
        async with self._sessions() as db:
            rows = (await db.execute(select(m.Mastery).where(m.Mastery.user_id == user_id))).scalars()
            return {r.node_key: MasteryState(r.node_key, r.p_mastery, r.evidence_count, list(r.contexts)) for r in rows}

    async def save_mastery(self, user_id: uuid.UUID, states: list[MasteryState], at: datetime) -> None:
        async with self._sessions() as db, db.begin():
            tenant = await self._tenant(db, user_id)
            for s in states:
                values = {
                    "p_mastery": s.p_mastery,
                    "evidence_count": s.evidence_count,
                    "contexts": s.contexts,
                    "contexts_count": len(s.contexts),
                    "last_evidence_at": at,
                }
                await db.execute(
                    insert(m.Mastery)
                    .values(id=uuid.uuid4(), tenant_id=tenant, user_id=user_id, node_key=s.node_key, **values)
                    .on_conflict_do_update(constraint="uq_mastery_user_node", set_=values)
                )

    async def tickets(self, user_id: uuid.UUID, active_only: bool = True) -> dict[str, Ticket]:
        async with self._sessions() as db:
            query = select(m.WeaknessTicket).where(m.WeaknessTicket.user_id == user_id)
            if active_only:
                query = query.where(m.WeaknessTicket.status.in_(["open", "reopened"]))
            return {r.node_key: _ticket(r) for r in (await db.execute(query)).scalars()}

    async def save_ticket(self, user_id: uuid.UUID, ticket: Ticket) -> None:
        async with self._sessions() as db, db.begin():
            row = (
                await db.execute(
                    select(m.WeaknessTicket).where(
                        m.WeaknessTicket.user_id == user_id, m.WeaknessTicket.node_key == ticket.node_key
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = m.WeaknessTicket(
                    tenant_id=await self._tenant(db, user_id), user_id=user_id, node_key=ticket.node_key
                )
                db.add(row)
            row.status, row.severity, row.priority, row.reopen_count = (
                ticket.status,
                ticket.severity,
                ticket.priority,
                ticket.reopen_count,
            )
            row.examples = [
                {"at": e.at.isoformat(), "text": e.text, "context": e.context} for e in ticket.examples[-20:]
            ]
            row.success_contexts = [{"at": s.at.isoformat(), "context": s.context} for s in ticket.successes]
            row.interventions = [{"kind": i} for i in ticket.interventions]

    async def recent_errors(self, user_id: uuid.UUID, node_key: str) -> list[datetime]:
        async with self._sessions() as db:
            row = (
                await db.execute(select(m.Mastery).where(m.Mastery.user_id == user_id, m.Mastery.node_key == node_key))
            ).scalar_one_or_none()
        times = [datetime.fromisoformat(t) for t in (row.error_times if row else [])]
        if not times:
            return []
        cutoff = max(times) - ERROR_WINDOW
        return [t for t in times if t > cutoff]

    async def record_error_time(self, user_id: uuid.UUID, node_key: str, at: datetime) -> None:
        async with self._sessions() as db, db.begin():
            row = (
                await db.execute(select(m.Mastery).where(m.Mastery.user_id == user_id, m.Mastery.node_key == node_key))
            ).scalar_one_or_none()
            if row is None:
                row = m.Mastery(
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    node_key=node_key,
                    p_mastery=0.15,
                    evidence_count=0,
                    contexts_count=0,
                    contexts=[],
                    error_times=[],
                )
                db.add(row)
            cutoff = at - ERROR_WINDOW
            kept = [t for t in row.error_times if datetime.fromisoformat(t) > cutoff]
            row.error_times = [*kept, at.isoformat()]

    async def posteriors(self, user_id: uuid.UUID) -> dict[tuple[str, str], BandPosterior]:
        async with self._sessions() as db:
            rows = (await db.execute(select(m.BandPosterior).where(m.BandPosterior.user_id == user_id))).scalars()
            return {(r.pack, r.skill): BandPosterior(r.mean, r.variance, r.observations) for r in rows}

    async def save_posterior(self, user_id: uuid.UUID, pack: str, skill: str, posterior: BandPosterior) -> None:
        async with self._sessions() as db, db.begin():
            values = {"mean": posterior.mean, "variance": posterior.variance, "observations": posterior.observations}
            await db.execute(
                insert(m.BandPosterior)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    pack=pack,
                    skill=skill,
                    **values,
                )
                .on_conflict_do_update(constraint="uq_band_posterior", set_=values)
            )

    async def fsrs(self, user_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        async with self._sessions() as db:
            rows = (await db.execute(select(m.FsrsItem).where(m.FsrsItem.user_id == user_id))).scalars()
            return {r.item_key: dict(r.card) for r in rows}

    async def save_fsrs(self, user_id: uuid.UUID, item_key: str, card: dict[str, Any]) -> None:
        async with self._sessions() as db, db.begin():
            values = {
                "card": card,
                "stability": card.get("stability"),
                "difficulty": card.get("difficulty"),
                "due_at": due_at(card),
            }
            await db.execute(
                insert(m.FsrsItem)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    item_key=item_key,
                    **values,
                )
                .on_conflict_do_update(constraint="uq_fsrs_user_item", set_=values)
            )

    async def fail_day_plan(self, session_id: uuid.UUID, reason: str) -> None:
        async with self._sessions() as db, db.begin():
            row = await db.get_one(m.Session, session_id)
            row.plan = {**row.plan, "status": "failed", "error": reason}

    async def save_day_plan(self, plan: DayPlan, session_id: uuid.UUID | None = None) -> uuid.UUID:
        async with self._sessions() as db, db.begin():
            if session_id is not None:
                existing = await db.get_one(m.Session, session_id)
                if existing.user_id != plan.user_id:
                    raise PermissionError("session belongs to another user")
                existing.plan = {**plan.model_dump(mode="json"), "status": "ready"}
                return existing.id
            row = m.Session(
                tenant_id=await self._tenant(db, plan.user_id),
                user_id=plan.user_id,
                kind="live",
                city=plan.city,
                started_at=datetime.now(UTC),
                plan=plan.model_dump(mode="json"),
            )
            db.add(row)
            await db.flush()
            return row.id

    async def world_state(self, user_id: uuid.UUID, city: str) -> dict[str, Any]:
        async with self._sessions() as db:
            row = (
                await db.execute(select(m.WorldState).where(m.WorldState.user_id == user_id, m.WorldState.city == city))
            ).scalar_one_or_none()
        if row is None:
            return {"story_flags": {}, "district_unlocks": [], "inventory": [], "flat": {}, "job": {}}
        return {
            "story_flags": row.story_flags,
            "district_unlocks": row.district_unlocks,
            "inventory": row.inventory,
            "flat": row.flat,
            "job": row.job,
        }

    async def save_world_state(self, user_id: uuid.UUID, city: str, state: dict[str, Any]) -> None:
        async with self._sessions() as db, db.begin():
            values = {
                k: state.get(k, default)
                for k, default in (
                    ("story_flags", {}),
                    ("district_unlocks", []),
                    ("inventory", []),
                    ("flat", {}),
                    ("job", {}),
                )
            }
            await db.execute(
                insert(m.WorldState)
                .values(
                    id=uuid.uuid4(), tenant_id=await self._tenant(db, user_id), user_id=user_id, city=city, **values
                )
                .on_conflict_do_update(constraint="uq_world_state_user_city", set_=values)
            )

    async def relationship(self, user_id: uuid.UUID, npc_key: str) -> tuple[float, str]:
        async with self._sessions() as db:
            row = (
                await db.execute(
                    select(m.NpcRelationship).where(
                        m.NpcRelationship.user_id == user_id, m.NpcRelationship.npc_key == npc_key
                    )
                )
            ).scalar_one_or_none()
        return (row.affinity, row.shared_history_summary) if row else (0.0, "")

    async def save_relationship(self, user_id: uuid.UUID, npc_key: str, affinity: float, summary: str) -> None:
        async with self._sessions() as db, db.begin():
            values = {"affinity": affinity, "shared_history_summary": summary}
            await db.execute(
                insert(m.NpcRelationship)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    npc_key=npc_key,
                    **values,
                )
                .on_conflict_do_update(constraint="uq_npc_rel_user_npc", set_=values)
            )

    async def save_notebook(self, user_id: uuid.UUID, session_id: uuid.UUID, notebook: dict[str, Any]) -> None:
        async with self._sessions() as db, db.begin():
            row = await db.get_one(m.Session, session_id)
            if row.user_id != user_id:
                raise PermissionError("session belongs to another user")
            row.plan = {**row.plan, "notebook": notebook}
            row.ended_at = row.ended_at or datetime.now(UTC)

    async def save_lesson(self, user_id: uuid.UUID, node_key: str, lesson: dict[str, Any]) -> uuid.UUID:
        async with self._sessions() as db, db.begin():
            row = m.Lesson(
                tenant_id=await self._tenant(db, user_id), user_id=user_id, node_key=node_key, content=lesson
            )
            db.add(row)
            await db.flush()
            return row.id

    async def apply_ledger(self, user_id: uuid.UUID, entries: list[LedgerEntry]) -> int:
        added = 0
        async with self._sessions() as db, db.begin():
            tenant = await self._tenant(db, user_id)
            wallet = (
                await db.execute(select(m.Wallet).where(m.Wallet.user_id == user_id).with_for_update())
            ).scalar_one()
            for entry in entries:
                inserted = (
                    await db.execute(
                        insert(m.Ledger)
                        .values(
                            id=uuid.uuid4(),
                            tenant_id=tenant,
                            user_id=user_id,
                            currency=entry.currency,
                            delta=entry.delta,
                            reason=entry.reason,
                            ref_id=entry.ref_id,
                            idempotency_key=entry.idempotency_key,
                        )
                        .on_conflict_do_nothing(index_elements=["idempotency_key"])
                        .returning(m.Ledger.id)
                    )
                ).first()
                if inserted is None:
                    continue
                added += 1
                if entry.currency == "coins":
                    if wallet.coins + entry.delta < 0:
                        raise ValueError("insufficient coins")
                    wallet.coins += entry.delta
                else:
                    wallet.stars_total += entry.delta
        return added

    async def wallet(self, user_id: uuid.UUID) -> tuple[int, int]:
        async with self._sessions() as db:
            row = (await db.execute(select(m.Wallet).where(m.Wallet.user_id == user_id))).scalar_one()
            return row.coins, row.stars_total

    async def save_crs_snapshot(self, user_id: uuid.UUID, value: int, breakdown: dict[str, Any]) -> None:
        async with self._sessions() as db, db.begin():
            db.add(
                m.SimCrsSnapshot(
                    tenant_id=await self._tenant(db, user_id),
                    user_id=user_id,
                    value=value,
                    breakdown=breakdown,
                    computed_at=datetime.now(UTC),
                )
            )

    async def latest_crs(self, user_id: uuid.UUID) -> int | None:
        async with self._sessions() as db:
            value = (
                await db.execute(
                    select(m.SimCrsSnapshot.value)
                    .where(m.SimCrsSnapshot.user_id == user_id)
                    .order_by(m.SimCrsSnapshot.computed_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return value

    async def save_language_band(self, user_id: uuid.UUID, language: str, band: int) -> None:
        async with self._sessions() as db, db.begin():
            profile = (
                await db.execute(select(m.LearnerProfile).where(m.LearnerProfile.user_id == user_id).with_for_update())
            ).scalar_one()
            bands = dict(profile.settings.get("language_bands", {}))
            bands[language] = band
            profile.settings = {**profile.settings, "language_bands": bands}

    async def active_days(self, user_id: uuid.UUID) -> list[date]:
        async with self._sessions() as db:
            rows = (
                await db.execute(
                    select(m.Session.started_at).where(m.Session.user_id == user_id, m.Session.kind == "live")
                )
            ).scalars()
            return sorted({r.date() for r in rows})

    async def save_mock(self, user_id: uuid.UUID, record: dict[str, Any]) -> uuid.UUID:
        async with self._sessions() as db, db.begin():
            row = m.MockExam(
                tenant_id=await self._tenant(db, user_id),
                user_id=user_id,
                pack=record["pack"],
                status="done",
                sections=record["sections"],
                raw_scores=record["raw_scores"],
                band_or_score=record["band_or_score"],
                clb_nclc=record["clb_nclc"],
            )
            db.add(row)
            await db.flush()
            return row.id

    async def mocks(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        async with self._sessions() as db:
            rows = (
                await db.execute(
                    select(m.MockExam).where(m.MockExam.user_id == user_id).order_by(m.MockExam.created_at)
                )
            ).scalars()
            return [
                {
                    "id": str(r.id),
                    "pack": r.pack,
                    "sections": r.sections,
                    "raw_scores": r.raw_scores,
                    "band_or_score": r.band_or_score,
                    "clb_nclc": r.clb_nclc,
                }
                for r in rows
            ]
