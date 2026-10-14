import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from lingard_contracts.assessment import DimensionScore, ErrorTag, Span, TargetEvidence, UtteranceAssessment
from lingard_contracts.events import TurnEvent
from lingard_db.base import make_engine, session_factory
from lingard_db.migrate import migrate
from lingard_db.models import LearnerProfile, Tenant, User
from lingard_graphs.pedagogy.bands import BandPosterior
from lingard_graphs.pedagogy.mastery import MasteryState
from lingard_graphs.pedagogy.review import new_card
from lingard_graphs.pedagogy.tickets import Example, Ticket
from lingard_graphs.sql_store import SqlStore
from lingard_graphs.store import LearnerProfileView, LearnerStore, MemoryStore, SceneRecord

from .test_scene_and_turn_graphs import brief, good_draft

USER = uuid.uuid4()


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[LearnerStore]:
    if request.param == "memory":
        memory = MemoryStore()
        memory.profiles[USER] = LearnerProfileView(USER, "Ernest", "ar", "tense", {}, {}, {"fr": 6})
        yield memory
        return
    async with request.getfixturevalue("pg_schema_factory")() as (url, schema):
        await asyncio.to_thread(migrate, url, schema)
        engine = make_engine(url, schema)
        sessions = session_factory(engine)
        async with sessions() as db, db.begin():
            tenant = Tenant(name="t")
            db.add(tenant)
            await db.flush()
            db.add(User(id=USER, tenant_id=tenant.id, display_name="Ernest", name_key="ernest", pin_hash="x"))
            await db.flush()
            db.add(
                LearnerProfile(
                    tenant_id=tenant.id,
                    user_id=USER,
                    l1="ar",
                    intensity_cap="tense",
                    settings={"language_bands": {"fr": 6}},
                )
            )
        yield SqlStore(sessions)
        await engine.dispose()


async def test_store_contract(store: LearnerStore) -> None:
    from lingard_contracts.scene import SceneContract

    profile = await store.profile(USER)
    assert profile.display_name == "Ernest" and profile.language_bands == {"fr": 6}

    draft = good_draft([])
    b = brief()
    contract = SceneContract.model_validate(
        {
            "city": b.city,
            "location_key": b.location_key,
            "cast": [{"npc_key": "landlord_martin", "role": "landlord", "voice_id": "v"}],
            "learner_goal": draft["learner_goal"],
            "targets": {
                "functions": ["fr.func.negotiate"],
                "grammar": ["fr.grammar.si_imparfait"],
                "lexset": ["fr.lex.housing.deposit_repairs"],
            },
            "elicitation": draft["elicitation"],
            "approved_facts": draft["approved_facts"],
            "npc_language_band": 7,
            "accent_variety": ["fr-FR-standard"],
            "success_conditions": draft["success_conditions"],
            "max_turns": 16,
            "exits": draft["exits"],
        }
    )
    session_id = uuid.uuid4()
    if isinstance(store, SqlStore):
        from lingard_contracts.planning import DayPlan, SceneBrief

        session_id = await store.save_day_plan(
            DayPlan(
                user_id=USER,
                city="rivemont",
                scenes=[
                    SceneBrief(
                        city="rivemont",
                        location_key=b.location_key,
                        npc_keys=["landlord_martin"],
                        story_beat="x",
                        targets=["fr.func.negotiate"],
                        learner_band=6,
                    )
                ],
            )
        )
    record = SceneRecord(scene_id=contract.scene_id, user_id=USER, session_id=session_id, contract=contract)
    await store.save_scene(record)
    loaded = await store.scene(contract.scene_id)
    assert loaded is not None and loaded.contract == contract
    assert [s.scene_id for s in await store.scenes_for_session(session_id)] == [contract.scene_id]

    event = TurnEvent(
        trace_id=uuid.uuid4(),
        user_id=USER,
        session_id=session_id,
        scene_id=contract.scene_id,
        turn_index=0,
        speaker="learner",
        language="fr-FR",
        transcript="si je refuserais",
    )
    assert await store.save_turn(event) is True
    assert await store.save_turn(event) is False
    assert [t.event_id for t in await store.turns(contract.scene_id)] == [event.event_id]

    span = Span(start=0, end=16, text="si je refuserais")
    assessment = UtteranceAssessment(
        turn_event_id=event.event_id,
        pack="tef_canada",
        dimensions=[DimensionScore(dimension="fluency", score=6, confidence=0.6)],
        error_tags=[ErrorTag(node_key="fr.grammar.si_imparfait", span=span, confidence=0.9, second_check_agrees=True)],
        target_evidence=[TargetEvidence(node_key="fr.grammar.si_imparfait", correct=False, span=span, confidence=0.9)],
        confidence=0.7,
    )
    assert not await store.assessment_exists(event.event_id)
    await store.save_assessment(USER, assessment)
    await store.save_assessment(USER, assessment)
    assert await store.assessment_exists(event.event_id)
    [again] = await store.assessments_for_scene(contract.scene_id)
    assert again.error_tags[0].showable and again.target_evidence[0].node_key == "fr.grammar.si_imparfait"

    now = datetime.now(UTC)
    await store.record_error_time(USER, "fr.grammar.si_imparfait", now - timedelta(days=40))
    await store.record_error_time(USER, "fr.grammar.si_imparfait", now)
    recent = await store.recent_errors(USER, "fr.grammar.si_imparfait")
    assert len(recent) == 1

    await store.save_mastery(USER, [MasteryState("fr.grammar.si_imparfait", 0.4, 3, ["a", "b"])], now)
    await store.save_mastery(USER, [MasteryState("fr.grammar.si_imparfait", 0.5, 4, ["a", "b", "c"])], now)
    mastery = await store.mastery(USER, ["fr.grammar.si_imparfait"])
    assert mastery["fr.grammar.si_imparfait"].p_mastery == 0.5 and len(await store.all_mastery(USER)) == 1

    ticket = Ticket(
        "fr.grammar.si_imparfait", examples=[Example(now, "si je refuserais", "ctx")], interventions=["recast_heavy"]
    )
    await store.save_ticket(USER, ticket)
    ticket.status = "closed"
    await store.save_ticket(USER, ticket)
    assert await store.tickets(USER) == {}
    assert (await store.tickets(USER, active_only=False))["fr.grammar.si_imparfait"].status == "closed"

    await store.save_posterior(USER, "tef_canada", "speaking", BandPosterior(300, 400, 2))
    assert (await store.posteriors(USER))[("tef_canada", "speaking")].mean == 300
    await store.save_fsrs(USER, "fr.grammar.si_imparfait", new_card())
    assert "fr.grammar.si_imparfait" in await store.fsrs(USER)
    await store.save_world_state(USER, "rivemont", {"story_flags": {"deposit": "half"}, "district_unlocks": ["a"]})
    assert (await store.world_state(USER, "rivemont"))["story_flags"] == {"deposit": "half"}
    await store.save_relationship(USER, "landlord_martin", 0.2, "Argued about the deposit.")
    assert await store.relationship(USER, "landlord_martin") == (0.2, "Argued about the deposit.")
    await store.save_notebook(USER, session_id, {"corrections": []})
    assert await store.save_lesson(USER, "fr.grammar.si_imparfait", {"title": "x"})
