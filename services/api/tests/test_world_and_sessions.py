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
    async with api.state.sessions() as db:
        await db.execute(update(LearnerProfile).values(settings={"language_bands": {"fr": 7}}))
        await db.commit()
    world = await api.client.get("/v1/world/rivemont", params={"hour": 12}, headers=api.bearer(token))
    assert all(d["unlocked"] for d in world.json()["districts"])
    assert (await api.client.get("/v1/world/atlantis", headers=api.bearer(token))).status_code == 422


async def test_session_plan_scene_view_hides_targets_and_live_dispatch(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    started = await api.client.post("/v1/sessions", json={"city": "rivemont"}, headers=api.bearer(token))
    assert started.status_code == 202
    session_id = started.json()["id"]
    jobs = api.state.jobs
    assert isinstance(jobs, MemoryJobQueue)
    assert jobs.jobs[-1][0] == GRAPH_JOBS and jobs.jobs[-1][1]["kind"] == "day_planner"

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

    live = await api.client.post(f"/v1/scenes/{contract.scene_id}/live", headers=api.bearer(token))
    assert live.status_code == 200 and live.json()["token"].count(".") == 2
    stream, payload = jobs.jobs[-1]
    assert stream == LIVE_JOBS and payload["contract"]["targets"]["grammar"] == ["fr.grammar.si_imparfait"]

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
