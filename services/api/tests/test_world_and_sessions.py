import uuid

from sqlalchemy import update

from lingard_api.jobs import GRAPH_JOBS, LIVE_JOBS, MemoryJobQueue
from lingard_db.models import LearnerProfile, Scene

PIN = "613470"


async def test_world_view_respects_band_unlocks(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    world = await api.client.get("/v1/world/rivemont", params={"hour": 12}, headers=api.bearer(token))
    assert world.status_code == 200
    districts = {d["key"]: d for d in world.json()["districts"]}
    assert districts["rivemont.vieux_port"]["unlocked"] and not districts["rivemont.saint_roch"]["unlocked"]
    for band, expected in ((7, {"rivemont.vieux_port", "rivemont.saint_roch"}), (8, set(districts))):
        async with api.state.sessions() as db:
            await db.execute(update(LearnerProfile).values(settings={"language_bands": {"fr": band}}))
            await db.commit()
        world = await api.client.get("/v1/world/rivemont", params={"hour": 12}, headers=api.bearer(token))
        assert {d["key"] for d in world.json()["districts"] if d["unlocked"]} == expected
    assert (await api.client.get("/v1/world/atlantis", headers=api.bearer(token))).status_code == 422


async def test_session_plan_scene_view_hides_targets_and_live_dispatch(api, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    unconfigured = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert unconfigured.status_code == 503 and "ANTHROPIC_API_KEY" in unconfigured.json()["detail"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # the graphs themselves run on the test's scripted models
    started = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert started.status_code == 202
    session_id = started.json()["id"]
    jobs = api.state.jobs
    assert isinstance(jobs, MemoryJobQueue)
    assert jobs.jobs[-1][0] == GRAPH_JOBS and jobs.jobs[-1][1]["kind"] == "day_planner"
    queued = len(jobs.jobs)
    again = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert again.json()["id"] == session_id and len(jobs.jobs) == queued, "a plan in progress is reused, not redone"

    from lingard_contracts.scene import SceneContract

    contract = SceneContract.model_validate(
        {
            "city": "rivemont",
            "location_key": "rivemont.vieux_port.apartment_3b",
            "cast": [{"npc_key": "landlord_martin", "role": "landlord", "voice_id": "fr_m_58_martin"}],
            "learner_goal": "Récupérer votre dépôt de garantie",
            "targets": {"grammar": ["fr.grammar.si_imparfait"]},
            "elicitation": [{"target": "fr.grammar.si_imparfait", "tactic": "Ask what the tenant would do if refused"}],
            "approved_facts": ["Le dépôt était de 900 dollars"],
            "npc_language_band": 7,
            "accent_variety": ["fr-FR-standard"],
            "success_conditions": ["counter-offer"],
            "max_turns": 12,
            "exits": [{"key": "deal", "trigger": "agree", "consequence": "partial refund"}],
        }
    )
    async with api.state.sessions() as db:
        from lingard_db.models import User

        user = (await db.execute(__import__("sqlalchemy").select(User))).scalar_one()
        db.add(
            Scene(
                id=contract.scene_id,
                tenant_id=user.tenant_id,
                user_id=user.id,
                session_id=uuid.UUID(session_id),
                contract=contract.model_dump(mode="json"),
            )
        )
        await db.commit()

    session = await api.client.get(f"/v1/sessions/{session_id}", headers=api.bearer(token))
    assert session.json()["scene_ids"] == [str(contract.scene_id)]
    scene = await api.client.get(f"/v1/scenes/{contract.scene_id}", headers=api.bearer(token))
    body = scene.json()
    assert body["learner_goal"] == "Récupérer votre dépôt de garantie"
    assert "targets" not in body and "elicitation" not in body and "si_imparfait" not in scene.text

    from lingard_db.models import Session

    async with api.state.sessions() as db:  # the planner has handed over the first scene; more are coming
        await db.execute(
            update(Session).where(Session.id == uuid.UUID(session_id)).values(plan={"status": "ready", "complete": False})
        )
        await db.commit()
    ahead = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert ahead.json()["id"] == session_id and len(jobs.jobs) == queued, "a day planned ahead is reused until played"
    assert ahead.json()["status"] == "ready" and ahead.json()["complete"] is False

    live = await api.client.post(f"/v1/scenes/{contract.scene_id}/live", headers=api.bearer(token))
    assert live.status_code == 200 and live.json()["token"].count(".") == 2
    stream, payload = jobs.jobs[-1]
    assert stream == LIVE_JOBS and payload["contract"]["targets"]["grammar"] == ["fr.grammar.si_imparfait"]
    played = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert played.json()["id"] != session_id, "once a scene of the day is played, starting plans a new day"

    other = await api.client.post("/v1/admin/users", json={"display_name": "Lina"}, headers=api.bearer(token))
    lina = (await api.sign_in("Lina", other.json()["one_time_pin"])).json()
    await api.client.post(
        "/v1/auth/change-pin",
        json={"current_pin": other.json()["one_time_pin"], "new_pin": "195837"},
        headers=api.bearer(lina["access_token"]),
    )
    lina_token = (await api.sign_in("Lina", "195837")).json()["access_token"]
    assert (await api.client.get(f"/v1/scenes/{contract.scene_id}", headers=api.bearer(lina_token))).status_code == 404
    assert (await api.client.get(f"/v1/sessions/{session_id}", headers=api.bearer(lina_token))).status_code == 404

    ended = await api.client.post(f"/v1/sessions/{session_id}/end", headers=api.bearer(token))
    assert ended.json()["status"] == "ended" and jobs.jobs[-1][1]["kind"] == "night_consolidation"


async def test_city_catalogue_comes_from_content(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    response = await api.client.get("/v1/world", headers=api.bearer(token))
    assert response.status_code == 200
    entries = {e["city"]: e for e in response.json()}
    assert entries["rivemont"] == {
        "city": "rivemont",
        "name": "Rivemont",
        "language": "fr",
        "pack": "tef_canada",
        "pack_name": "TEF Canada",
        "level_scale": "NCLC",
    }
    assert entries["ashford"]["pack_name"] == "IELTS General Training"
    world = await api.client.get("/v1/world/ashford", headers=api.bearer(token))
    assert world.json()["palette"]["sky"] == ["#dfe6ee", "#9aa9bd"]


async def test_location_art_is_served_without_sign_in(api) -> None:  # type: ignore[no-untyped-def]
    response = await api.client.get("/v1/art/rivemont/vieux_port/apartment_bg.svg")
    assert response.status_code == 200 and response.text.startswith("<svg")
    assert (await api.client.get("/v1/art/../city.yaml")).status_code == 404
