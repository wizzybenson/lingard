import uuid

from sqlalchemy import select

from lingard_api.routes.today import skill_status
from lingard_db.models import Lesson, User
from lingard_live.tts import ScriptedTts

from .test_phase2_to_5_api import learner

GAME = {"kind": "dictation", "items": [{"prompt": "…", "answer": "Je voudrais un café.", "node_key": "fr.grammar.x"}]}


async def _lesson(api, user_id: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with api.state.sessions() as db:
        user = await db.get_one(User, uuid.UUID(user_id))
        row = Lesson(
            tenant_id=user.tenant_id,
            user_id=user.id,
            node_key="fr.grammar.conditionnel_present",
            content={"title": "Le conditionnel", "games": [GAME]},
        )
        db.add(row)
        await db.commit()
        return row.id


def test_skill_status_reads_the_whole_range() -> None:
    assert skill_status(7, 7, 9) == "met"
    assert skill_status(7, 5, 8) == "close"
    assert skill_status(7, 4, 6) == "behind"
    assert skill_status(7, None, None) == "unknown"


async def test_today_guides_a_new_learner_then_counts_any_practice(api) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await learner(api)
    first = (await api.client.get("/v1/today", headers=api.bearer(token))).json()
    assert first["next_step"] == "set_goal" and first["streak"] == 0 and first["goals"] == []
    assert first["onboarding"] == {"goal": False, "placement": False, "first_story": False}

    goal = {"exam_dates": {"tef_canada": "2027-03-01"}, "target_bands": {"tef_canada": {"speaking": 9}}}
    profile = (await api.client.patch("/v1/me", json=goal, headers=api.bearer(token))).json()
    assert profile["exam_dates"] == {"tef_canada": "2027-03-01"}
    assert profile["target_bands"]["tef_canada"] == {"listening": 7, "reading": 7, "writing": 7, "speaking": 9}
    bad = await api.client.patch(
        "/v1/me", json={"target_bands": {"tef_canada": {"speaking": 12}}}, headers=api.bearer(token)
    )
    assert bad.status_code == 422

    after_goal = (await api.client.get("/v1/today", headers=api.bearer(token))).json()
    assert after_goal["next_step"] == "placement"
    assert after_goal["onboarding"]["goal"] is True and after_goal["onboarding"]["placement"] is False
    tef = after_goal["goals"][0]
    assert tef["pack_name"] == "TEF Canada" and tef["days_left"] > 0
    assert {s["skill"]: s["target"] for s in tef["skills"]}["speaking"] == 9

    lesson_id = await _lesson(api, user_id)
    assert (await api.client.get("/v1/today", headers=api.bearer(token))).json()["lessons_waiting"] == 1
    done = await api.client.post(
        f"/v1/lessons/{lesson_id}/complete", json={"correct": 4, "total": 5}, headers=api.bearer(token)
    )
    assert done.json() == {"status": "done", "passed": True}
    again = await api.client.post(
        f"/v1/lessons/{lesson_id}/complete", json={"correct": 0, "total": 5}, headers=api.bearer(token)
    )
    assert again.json()["status"] == "done"
    wallet = (await api.client.get("/v1/wallet", headers=api.bearer(token))).json()
    assert wallet["coins"] >= 25 and sum(e["reason"] == "lesson_complete" for e in wallet["recent"]) == 1
    final = (await api.client.get("/v1/today", headers=api.bearer(token))).json()
    assert final["streak"] == 1 and final["practised_today"] and final["lessons_waiting"] == 0
    store = api.state.graph_deps.store
    assert "fr.grammar.conditionnel_present" in await store.fsrs(uuid.UUID(user_id))


async def test_lesson_audio_and_writing_tasks(api) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await learner(api)
    lesson_id = await _lesson(api, user_id)
    url = f"/v1/lessons/{lesson_id}/audio"
    assert (await api.client.get(url, params={"game": 0, "item": 0}, headers=api.bearer(token))).status_code == 503
    api.state.tts = tts = ScriptedTts()
    spoken = await api.client.get(url, params={"game": 0, "item": 0}, headers=api.bearer(token))
    assert spoken.status_code == 200 and spoken.content[:4] == b"RIFF" and tts.spoken == ["Je voudrais un café."]
    assert (await api.client.get(url, params={"game": 3, "item": 0}, headers=api.bearer(token))).status_code == 404
    other, _ = await learner(api, "Omar")
    assert (await api.client.get(url, params={"game": 0, "item": 0}, headers=api.bearer(other))).status_code == 404

    tasks = (await api.client.get("/v1/writing/tasks", headers=api.bearer(token))).json()
    assert {(t["pack"], t["task_id"]) for t in tasks} == {
        ("ielts_gt", "task1_letter"),
        ("ielts_gt", "task2_essay"),
        ("tef_canada", "section_a"),
        ("tef_canada", "section_b"),
    }
    assert all(len(t["prompts"]) == 3 and t["min_words"] > 0 for t in tasks)
    unconfigured = await api.client.post(
        "/v1/writing",
        json={"pack": "ielts_gt", "task_id": "task1_letter", "prompt": "p", "text": "t"},
        headers=api.bearer(token),
    )
    assert unconfigured.status_code == 503
    async with api.state.sessions() as db:
        assert (await db.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one().status == "planned"
