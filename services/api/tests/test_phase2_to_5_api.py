import io
import json
import wave
import zipfile

import numpy as np
from sqlalchemy import select

from lingard_db.models import AuditLog, User, VoiceProfile
from lingard_economy.rewards import LedgerEntry
from lingard_live.tts import ScriptedTts
from lingard_pronunciation.clone import FakeClone
from lingard_storage import AUDIO_BUCKET, MemoryObjectStore, user_prefix

PIN = "613470"


def wav(seconds: float) -> bytes:
    samples = (3000 * np.sin(np.arange(int(16000 * seconds)) * 0.05)).astype(np.int16).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(samples)
    return buffer.getvalue()


async def learner(api, name: str = "Lina") -> tuple[str, str]:  # type: ignore[no-untyped-def]
    if not hasattr(api, "admin"):
        api.admin = await api.admin_token()
    admin = api.admin
    created = (await api.client.post("/v1/admin/users", json={"display_name": name}, headers=api.bearer(admin))).json()
    first = (await api.sign_in(name, created["one_time_pin"])).json()
    await api.client.post(
        "/v1/auth/change-pin",
        json={"current_pin": created["one_time_pin"], "new_pin": "195837"},
        headers=api.bearer(first["access_token"]),
    )
    token = (await api.sign_in(name, "195837")).json()["access_token"]
    return token, created["user_id"]


async def test_placement_skip_passport_and_thread_ownership(api, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    token, _ = await learner(api)
    started = await api.client.post("/v1/placement", json={"language": "fr", "path": "skip"}, headers=api.bearer(token))
    assert started.status_code == 201 and started.json()["done"] is True
    assert started.json()["result"]["start_district"] == "rivemont.vieux_port"
    passport = (await api.client.get("/v1/passport", headers=api.bearer(token))).json()
    assert len(passport["bands"]) == 4 and all(b["low80"] < b["mean"] < b["high80"] for b in passport["bands"])
    assert "not an official assessment" in passport["disclaimer"]
    body = {"language": "fr", "path": "quick"}
    unconfigured = await api.client.post("/v1/placement", json=body, headers=api.bearer(token))
    assert unconfigured.status_code == 503 and "text-to-speech" in unconfigured.json()["detail"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # the graphs run on the test's scripted models
    api.state.tts = ScriptedTts()
    quick = await api.client.post("/v1/placement", json=body, headers=api.bearer(token))
    thread = quick.json()["thread_id"]
    assert quick.json()["prompt"]["kind"] == "item" and "answer" not in json.dumps(quick.json()["prompt"])
    other, _ = await learner(api, "Omar")
    stolen = await api.client.post(f"/v1/threads/{thread}/answer", json={"value": 0}, headers=api.bearer(other))
    assert stolen.status_code == 404


async def test_writing_lessons_wallet_and_shop(api, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await learner(api)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # scoring runs on the test's scripted models
    bad = await api.client.post(
        "/v1/writing",
        json={"pack": "ielts_gt", "task_id": "nope", "prompt": "p", "text": "t"},
        headers=api.bearer(token),
    )
    assert bad.status_code == 422
    ok = await api.client.post(
        "/v1/writing",
        json={"pack": "ielts_gt", "task_id": "task1_letter", "prompt": "p", "text": "Dear Sir"},
        headers=api.bearer(token),
    )
    assert ok.status_code == 202 and api.state.jobs.jobs[-1][1]["kind"] == "writing_review"
    poor = await api.client.post("/v1/shop/flat_upgrade", headers=api.bearer(token))
    assert poor.status_code == 409
    import uuid as uuid_mod

    await api.state.graph_deps.store.apply_ledger(
        uuid_mod.UUID(user_id), [LedgerEntry("coins", 500, "quest_complete", "s1", "quest:s1")]
    )
    bought = await api.client.post("/v1/shop/flat_upgrade", headers=api.bearer(token))
    assert bought.status_code == 200 and bought.json()["coins"] == 100
    flat = next(i for i in bought.json()["items"] if i["key"] == "flat_upgrade")
    assert flat == {"key": "flat_upgrade", "price": 400, "held": 1, "limit": 3}
    world = (await api.client.get("/v1/world/ashford", headers=api.bearer(token))).json()
    homes = [loc for d in world["districts"] for loc in d["locations"] if loc["kind"] == "home"]
    assert homes and homes[0]["layer_art"][-1] == "decor/flat_1.svg", "the upgrade shows in the learner's home"
    assert (await api.client.get("/v1/league", headers=api.bearer(token))).json() == {"opted_in": False, "ranking": []}


async def test_voice_clone_passage_is_in_the_learners_language(api) -> None:  # type: ignore[no-untyped-def]
    token, _ = await learner(api)
    fr = (await api.client.get("/v1/voice/passage", params={"language": "fr"}, headers=api.bearer(token))).json()
    en = (await api.client.get("/v1/voice/passage", params={"language": "en"}, headers=api.bearer(token))).json()
    assert "français" in fr["text"] and "English" in en["text"]
    assert len(fr["text"].split()) >= 60, "about 30 s or more at a learner's pace"
    assert fr["min_seconds"] == 20 and fr["max_seconds"] == 120


async def test_voice_clone_consent_cascade_export_and_account_deletion(api, m4a) -> None:  # type: ignore[no-untyped-def]
    fake = FakeClone(name="voicebox")
    api.state.clone_providers = {"voicebox": fake}
    store = api.state.objects
    assert isinstance(store, MemoryObjectStore)
    token, user_id = await learner(api)
    files = {"sample": ("s.wav", wav(30), "audio/wav")}
    refused = await api.client.post("/v1/voice/clone", files=files, data={"consent": "true"}, headers=api.bearer(token))
    assert refused.status_code == 403, "profile consent is required too"
    await api.client.patch("/v1/me", json={"consents": {"voice_clone": True}}, headers=api.bearer(token))
    short = await api.client.post(
        "/v1/voice/clone",
        files={"sample": ("s.wav", wav(5), "audio/wav")},
        data={"consent": "true"},
        headers=api.bearer(token),
    )
    assert short.status_code == 422
    fake.fail_create = True
    failed = await api.client.post("/v1/voice/clone", files=files, data={"consent": "true"}, headers=api.bearer(token))
    assert failed.status_code == 502 and "provider unavailable" in failed.json()["detail"]
    fake.fail_create = False
    phone = {"sample": ("s.m4a", m4a(25), "audio/mp4")}
    created = await api.client.post("/v1/voice/clone", files=phone, data={"consent": "true"}, headers=api.bearer(token))
    assert created.status_code == 201 and len(fake.profiles) == 1, "a phone's M4A recording is accepted"
    assert abs(len(next(iter(fake.profiles.values()))) / 32_000 - 25) < 0.5, "decoded to 16 kHz mono"
    await store.put(AUDIO_BUCKET, f"{user_prefix(user_id)}turns/2026-10-01/t1.pcm", b"turn-audio")

    export = await api.client.get("/v1/me/export", headers=api.bearer(token))
    archive = zipfile.ZipFile(io.BytesIO(export.content))
    names = archive.namelist()
    assert "account.json" in names and "audio/turns/2026-10-01/t1.pcm" in names
    assert not any("voice/" in n for n in names)
    assert "pin_hash" not in archive.read("account.json").decode()
    assert "provider_profile_id" not in archive.read("data/voice_profiles.json").decode()

    deleted = await api.client.delete("/v1/voice/clone", headers=api.bearer(token))
    assert deleted.status_code == 204 and fake.profiles == {}
    assert await store.list_keys(AUDIO_BUCKET, f"{user_prefix(user_id)}voice/") == []
    async with api.state.sessions() as db:
        row = (await db.execute(select(VoiceProfile))).scalar_one()
        assert row.deleted_at is not None and row.status == "deleted"

    wrong = await api.client.post("/v1/me/delete", json={"pin": "000111"}, headers=api.bearer(token))
    assert wrong.status_code == 403
    gone = await api.client.post("/v1/me/delete", json={"pin": "195837"}, headers=api.bearer(token))
    assert gone.status_code == 204
    assert await store.list_keys(AUDIO_BUCKET, user_prefix(user_id)) == []
    assert (await api.sign_in("Lina", "195837")).status_code == 401
    async with api.state.sessions() as db:
        assert (await db.execute(select(User).where(User.name_key == "lina"))).scalar_one_or_none() is None
        actions = set((await db.execute(select(AuditLog.action))).scalars())
        rows = (await db.execute(select(AuditLog.action, AuditLog.target))).all()
        targets = " ".join(str(t) for _, t in rows)
    assert {"voice_clone_created", "voice_clone_deleted", "data_exported", "account_deleted"} <= actions
    assert user_id not in targets, "the audit trail does not keep the deleted learner's id"


async def test_glance_queue_and_offline_answer(api) -> None:  # type: ignore[no-untyped-def]
    token, _ = await learner(api)
    quests = (await api.client.get("/v1/glance", params={"language": "fr"}, headers=api.bearer(token))).json()
    assert len(quests) == 8 and all(q["kind"] == "read" for q in quests)
    await api.client.patch(
        "/v1/me", json={"exam_dates": {"ielts_gt": "2027-03-01", "tef_canada": "2027-03-01"}}, headers=api.bearer(token)
    )
    mixed = (await api.client.get("/v1/glance", headers=api.bearer(token))).json()
    assert [q["language"] for q in mixed[:4]] == ["fr", "en", "fr", "en"], "both exams' languages, taken in turn"
    first = quests[0]
    result = await api.client.post(
        "/v1/glance/answer",
        params={"language": "fr"},
        json={"quest_id": first["id"], "answer": 0, "synced_at": "2026-10-14T08:00:00Z"},
        headers=api.bearer(token),
    )
    body = result.json()
    assert result.status_code == 200 and isinstance(body["correct"], bool)
    assert body["correct"] == (body["answer"] == 0) and 0 <= body["answer"] < len(first["options"])


async def test_shop_items_take_effect_and_rewards_are_per_learner(api) -> None:  # type: ignore[no-untyped-def]
    import uuid as uuid_mod
    from datetime import UTC, datetime

    from lingard_db.models import Scene, Session, User

    token, user_id = await learner(api, "Ines")
    auth, user = api.bearer(token), uuid_mod.UUID(user_id)
    store = api.state.graph_deps.store
    _, other_id = await learner(api, "Yara")
    day = LedgerEntry("coins", 10, "streak_day", "2026-10-20", "streak:2026-10-20")
    assert await store.apply_ledger(uuid_mod.UUID(other_id), [day]) == 1
    assert await store.apply_ledger(user, [day]) == 1, "every learner earns the day's streak coins"
    await store.apply_ledger(user, [LedgerEntry("coins", 300, "quest_complete", "s1", "quest:s1")])

    freezes = [await api.client.post("/v1/shop/streak_freeze", headers=auth) for _ in range(3)]
    assert [r.status_code for r in freezes] == [200, 200, 409], "two spare freezes at most"
    assert (await api.client.get("/v1/today", headers=auth)).json()["freezes"] == 2

    cafe = await api.client.post("/v1/shop/cafe_visit", json={"city": "rivemont"}, headers=auth)
    assert cafe.status_code == 200
    assert (await store.world_state(user, "rivemont"))["inventory"] == ["cafe_visit"]

    gift = {"city": "rivemont", "npc_key": "landlord_martin"}
    assert (await api.client.post("/v1/shop/npc_gift", json=gift, headers=auth)).status_code == 409, "not met yet"
    async with api.state.sessions() as db:
        tenant = (await db.get(User, user)).tenant_id
        played = Session(tenant_id=tenant, user_id=user, kind="live", city="rivemont")
        played.started_at = datetime.now(UTC)
        db.add(played)
        await db.flush()
        for npc in ("examinatrice_claire", "landlord_martin"):  # an examiner from before decision 0019 too
            contract = {"cast": [{"npc_key": npc}]}
            db.add(Scene(tenant_id=tenant, user_id=user, session_id=played.id, contract=contract, status="done"))
        await db.commit()
    friends = (await api.client.get("/v1/shop/friends", params={"city": "rivemont"}, headers=auth)).json()
    assert [f["npc_key"] for f in friends] == ["landlord_martin"] and not friends[0]["gifted_today"], "no examiners"
    nowhere = await api.client.get("/v1/shop/friends", params={"city": "atlantis"}, headers=auth)
    assert nowhere.status_code == 422
    given = await api.client.post("/v1/shop/npc_gift", json=gift, headers=auth)
    assert given.status_code == 200 and given.json()["coins"] == 310 - 100 - 30 - 60
    assert (await store.relationship(user, "landlord_martin"))[0] == 0.2
    assert "gift_landlord_martin" in (await store.world_state(user, "rivemont"))["story_flags"]
    again = await api.client.post("/v1/shop/npc_gift", json=gift, headers=auth)
    assert again.status_code == 409 and again.json()["detail"] == "Already given today"
    assert (await api.client.get("/v1/wallet", headers=auth)).json()["coins"] == 120


async def test_draw_day_uses_real_rounds_and_pays_the_invitation_once(api) -> None:  # type: ignore[no-untyped-def]
    import uuid as uuid_mod

    from lingard_api.cli import seed_draws
    from lingard_economy.events import load_draws

    path = api.settings.content_root / "crs" / "draws.yaml"
    rounds = load_draws(path)
    french = next(d for d in rounds if d.category == "french")
    cec = next(d for d in rounds if d.category == "cec")
    assert await seed_draws(api.state, path) == len(rounds)
    assert await seed_draws(api.state, path) == 0, "seeding again adds nothing"
    token, user_id = await learner(api, "Noor")
    auth, user = api.bearer(token), uuid_mod.UUID(user_id)
    assert (await api.client.get("/v1/draws/latest", headers=auth)).json()["draw"] is None, "no exam chosen yet"

    await api.client.patch("/v1/me", json={"exam_dates": {"ielts_gt": "2027-03-01"}}, headers=auth)
    english = (await api.client.get("/v1/draws/latest", headers=auth)).json()
    assert english["draw"]["category"] == "cec" and english["draw"]["cutoff"] == cec.cutoff

    await api.client.patch(
        "/v1/me", json={"exam_dates": {"ielts_gt": "2027-03-01", "tef_canada": "2027-03-01"}}, headers=auth
    )
    before = (await api.client.get("/v1/draws/latest", headers=auth)).json()
    assert before["draw"]["category"] == "french" and before["draw"]["cutoff"] == french.cutoff
    assert "canada.ca" in before["draw"]["source_note"]
    assert before["invited"] is False, "no simulated score yet"
    await api.state.graph_deps.store.save_crs_snapshot(user, french.cutoff + 5, {})
    coins = (await api.client.get("/v1/wallet", headers=auth)).json()["coins"]
    for _ in range(2):
        invited = (await api.client.get("/v1/draws/latest", headers=auth)).json()
        assert invited["invited"] is True and invited["margin"] == 5
    assert (await api.client.get("/v1/wallet", headers=auth)).json()["coins"] == coins + invited["reward"]


async def test_preparing_without_an_exam_date_is_a_goal(api) -> None:  # type: ignore[no-untyped-def]
    """A learner who doesn't know their exam date yet still moves past "Set your goal" (it used to drop the goal)."""
    token, _ = await learner(api, "Tariq")
    auth = api.bearer(token)
    await api.client.patch("/v1/me", json={"exam_dates": {"tef_canada": ""}}, headers=auth)
    me = (await api.client.get("/v1/me", headers=auth)).json()
    assert me["exam_dates"] == {"tef_canada": None}
    today = (await api.client.get("/v1/today", headers=auth)).json()
    assert today["onboarding"]["goal"] is True and today["next_step"] == "placement"
    await api.client.patch("/v1/me", json={"exam_dates": {"tef_canada": None}}, headers=auth)
    assert (await api.client.get("/v1/me", headers=auth)).json()["exam_dates"] == {}, "null stops preparing"
