"""The learning coach's memory (decision 0029): mistakes over the last weeks, relapses after a lesson, and its journal
read back with what came of each suggestion."""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from lingard_api import coaching
from lingard_api.coach import Signals
from lingard_api.coaching import Picture, history, remember
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_db.models import Assessment, LearnerProfile, Scene, Session, Turn, User
from lingard_graphs.agents.learning_coach import CoachBrief, CoachPlan, RuleCandidate, SoundCandidate

from .test_phase2_to_5_api import learner


def tag(node_key: str, said: str, better: str, confidence: float = 0.92, agrees: bool = True) -> dict[str, Any]:
    return {
        "node_key": node_key,
        "span": {"start": 0, "end": len(said), "text": said},
        "correction": better,
        "confidence": confidence,
        "second_check_agrees": agrees,
    }


async def played_scene(api, user_id: str, tags: list[dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]
    """A scene played in Rivemont whose one learner turn carries these error tags."""
    async with api.state.sessions() as db:
        user = await db.get_one(User, uuid.UUID(user_id))
        session = Session(tenant_id=user.tenant_id, user_id=user.id, kind="live", city="rivemont",
                          started_at=datetime.now(UTC), plan={"status": "ready"})  # fmt: skip
        db.add(session)
        await db.flush()
        scene = Scene(tenant_id=user.tenant_id, user_id=user.id, session_id=session.id, contract={}, status="ended")
        db.add(scene)
        await db.flush()
        turn = Turn(tenant_id=user.tenant_id, user_id=user.id, scene_id=scene.id, event_id=uuid.uuid4(), index=0,
                    speaker="learner", transcript="…")  # fmt: skip
        db.add(turn)
        await db.flush()
        db.add(Assessment(tenant_id=user.tenant_id, user_id=user.id, turn_id=turn.id, pack="tef_canada",
                          dimension_scores=[], confidence=0.9, error_tags=tags))  # fmt: skip
        await db.commit()


async def test_the_path_mends_relapses_first_and_remembers_mistakes_across_scenes(api) -> None:  # type: ignore[no-untyped-def]
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    token, user_id = await learner(api)
    auth = api.bearer(token)
    await api.client.patch("/v1/me", json={"exam_dates": {"tef_canada": "2027-03-01"}}, headers=auth)
    await api.client.post("/v1/placement", json={"language": "fr", "path": "skip"}, headers=auth)
    points = (await api.client.get("/v1/key-points", params={"language": "fr"}, headers=auth)).json()
    learned, other = [k["node_key"] for k in points if k["core"] and k["kind"] == "grammar"][:2]
    lesson = (await api.client.post(f"/v1/key-points/{learned}", headers=auth)).json()["id"]
    await api.client.post(f"/v1/lessons/{lesson}/complete", json={"correct": 5, "total": 5}, headers=auth)

    await played_scene(api, user_id, [tag(other, "je mange hier", "j'ai mangé hier")])
    await played_scene(
        api, user_id, [tag(other, "je bois hier", "j'ai bu hier"), tag(learned, "il parle", "ils parlent")]
    )
    await played_scene(api, user_id, [tag(other, "x", "y", confidence=0.5), tag(other, "z", "w", agrees=False)])

    today = (await api.client.get("/v1/today", headers=auth)).json()
    assert today["coach"] == "rules", "no language model in tests: the curriculum's order stands"
    fix = next(s for s in today["path"] if s["kind"] == "fix")
    assert fix["node_key"] == learned, "a mistake made again after its lesson (a relapse) is mended first"
    assert fix["said"] == "il parle" and fix["better"] == "ils parlent", "quoted in the learner's own words"
    assert today["path"][-1]["kind"] != "learn", "a mistake to mend displaces the new rule"
    assert "story" in [s["kind"] for s in today["path"] if s["done"]], "a scene played today ticks the story"

    async with api.state.sessions() as db:
        uid = uuid.UUID(user_id)
        profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == uid))).scalar_one()
        picture = await coaching._gather(api.state, db, uid, profile, "fr", 0)
    slips = {s.node_key: s for s in picture.signals.slips}
    assert slips[learned].relapse and not slips[other].relapse
    assert slips[other].times == 2, "once per scene; never an unconfirmed one (low confidence, no second check)"
    assert slips[other].said == "je bois hier" and slips[other].days_ago == 0, "the latest words, and when"


def test_the_journal_keeps_each_days_plan_and_reads_back_what_came_of_it() -> None:
    brief = CoachBrief(
        language="fr", band=6, exam_name="TEF Canada", explain_language="English",
        rules=[RuleCandidate(node_key="fr.grammar.imparfait", title="Imparfait", kind="grammar", band=6, in_use=0.3)],
        sounds=[SoundCandidate(drill="fr.pron.u_vs_ou", title="/y/ et /u/", score=41.0)],
    )  # fmt: skip
    plan = CoachPlan(learn="fr.grammar.imparfait", sound="fr.pron.u_vs_ou", focus="This week: the past.")
    journal: dict[str, Any] = {}
    today = date(2026, 10, 22)
    for back in range(20, 0, -1):
        journal = remember(journal, "fr", (today - timedelta(days=back)).isoformat(), plan, brief)
    journal = remember(journal, "fr", (today - timedelta(days=1)).isoformat(), plan, brief)
    assert len(journal["fr"]) == 14, "two weeks kept, a later plan the same day replacing the earlier one"
    yesterday = journal["fr"][(today - timedelta(days=1)).isoformat()]
    assert yesterday["titles"] == {"fr.grammar.imparfait": "Imparfait", "fr.pron.u_vs_ou": "/y/ et /u/"}
    assert yesterday["sound_score"] == 41.0 and yesterday["focus"] == "This week: the past."

    picture = Picture(
        today=today,
        signals=Signals(story_ready=True),
        steps=[SimpleNamespace(node_key="fr.grammar.imparfait", status="open")],  # type: ignore[list-item]
        gym=SimpleNamespace(drills=[SimpleNamespace(key="fr.pron.u_vs_ou", score=63.0)]),  # type: ignore[arg-type]
        played_days={today - timedelta(days=1)},
    )
    lines = history(journal["fr"], picture, {(today - timedelta(days=1)).isoformat(): ["sounds"]})
    assert lines[0] == (
        "yesterday: suggested learn Imparfait (started); sound /y/ et /u/ (score 41 → 63). They did: sounds, story."
    ), "what it suggested, and what came of it"
    assert lines[1].startswith("2 days ago: ") and lines[1].endswith("They did: nothing.")
    assert len(lines) == 7, "a week read back"
