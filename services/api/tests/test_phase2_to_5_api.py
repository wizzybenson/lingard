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


async def test_writing_lessons_wallet_and_shop(api) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await learner(api)
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
    assert (await api.client.get("/v1/league", headers=api.bearer(token))).json() == {"opted_in": False, "ranking": []}


async def test_voice_clone_consent_cascade_export_and_account_deletion(api) -> None:  # type: ignore[no-untyped-def]
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
    created = await api.client.post("/v1/voice/clone", files=files, data={"consent": "true"}, headers=api.bearer(token))
    assert created.status_code == 201 and len(fake.profiles) == 1
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
    first = quests[0]
    result = await api.client.post(
        "/v1/glance/answer",
        params={"language": "fr"},
        json={"quest_id": first["id"], "answer": 0, "synced_at": "2026-10-14T08:00:00Z"},
        headers=api.bearer(token),
    )
    assert result.status_code == 200 and isinstance(result.json()["correct"], bool)
