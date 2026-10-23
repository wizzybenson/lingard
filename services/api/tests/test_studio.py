import math
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
from sqlalchemy import select

from lingard_db.models import User, VoiceProfile
from lingard_live.audio import pcm_to_wav, wav_to_pcm
from lingard_live.tts import ScriptedTts
from lingard_pronunciation import watermark
from lingard_pronunciation.app import Engines, create_app
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.golden_self import GoldenSelf, MemoryCache
from lingard_pronunciation.server import load_targets

PIN = "613470"


class LexiconRecognizer:
    """Hears exactly the expected phonemes, except one swap (to simulate an accent)."""

    def __init__(
        self,
        g2p: LexiconG2P,
        line: str,
        language: str,
        swap: dict[str, str] | None = None,
        before: list[str] | None = None,
    ) -> None:
        """``before``: sounds heard ahead of the line (a recording that starts with an "euh")."""
        self.expected = [*(before or []), *g2p.phonemes(line, language)]
        self.swap = swap or {}
        self.inventory = ["<b>", *sorted(set(self.expected) | set(self.swap.values()))]

    def log_posteriors(self, pcm: bytes) -> np.ndarray:
        rows = []
        for phoneme in self.expected:
            heard = self.inventory.index(self.swap.get(phoneme, phoneme))
            for _ in range(4):
                row = np.full(len(self.inventory), math.log(0.02))
                row[heard] = math.log(0.9)
                rows.append(row)
            blank = np.full(len(self.inventory), math.log(0.02))
            blank[0] = math.log(0.9)
            rows.append(blank)
        return np.array(rows)


def _wav() -> bytes:
    t = np.arange(8000) / 16_000
    return pcm_to_wav((0.3 * 32767 * np.sin(2 * np.pi * 180 * t)).astype(np.int16).tobytes())


def _attach(api, recognizer: LexiconRecognizer) -> None:  # type: ignore[no-untyped-def]
    root = api.settings.content_root
    app = create_app(Engines(LexiconG2P(root), None, recognizer, load_targets(root)))
    api.state.pronunciation = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pron")


async def test_studio_lines_come_from_content(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    response = await api.client.get("/v1/studio/items", params={"language": "en"}, headers=api.bearer(token))
    assert response.status_code == 200
    lines = response.json()
    assert {"node_key": "en.pron.th_sounds", "line": "Three, please."}.items() <= lines[0].items()


async def test_shadow_scores_and_reviews_on_final_attempt(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    line = "Un pain, pas un bain."
    form = {"line": line, "language": "fr", "attempt": "1"}
    files = {"audio": ("a.wav", _wav(), "audio/wav")}

    unconfigured = await api.client.post("/v1/studio/shadow", data=form, files=files, headers=api.bearer(token))
    assert unconfigured.status_code == 503

    _attach(api, LexiconRecognizer(LexiconG2P(api.settings.content_root), line, "fr", swap={"p": "b", "ɛ̃": "ɑ̃"}))
    first = await api.client.post("/v1/studio/shadow", data=form, files=files, headers=api.bearer(token))
    assert first.status_code == 200, first.text
    body = first.json()
    assert "fr.pron.p_vs_b" in body["critical"] and not body["passed"]
    assert body["final"] is False and body["attempts_left"] == 2
    assert body["pitch"]["reference"] == []  # no golden-self render yet: intonation not scored

    async with api.state.sessions() as db:
        user_id = (await db.execute(select(User.id))).scalar_one()  # the only account in this test
    store = api.state.graph_deps.store
    assert "fr.pron.p_vs_b" not in await store.fsrs(user_id)  # retries don't touch the schedule
    _attach(api, LexiconRecognizer(LexiconG2P(api.settings.content_root), line, "fr"))
    second = await api.client.post(
        "/v1/studio/shadow", data={**form, "attempt": "2"}, files=files, headers=api.bearer(token)
    )
    assert second.json()["passed"] and second.json()["final"]
    assert "fr.pron.p_vs_b" in await store.fsrs(user_id)

    unknown = await api.client.post(
        "/v1/studio/shadow", data={**form, "line": "Bonjour tout le monde."}, files=files, headers=api.bearer(token)
    )
    assert unknown.status_code == 404


async def test_reference_render_feeds_listening_and_intonation(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    line = "Un pain, pas un bain."
    params = {"line": line, "language": "fr"}

    no_tts = await api.client.get("/v1/studio/reference", params=params, headers=api.bearer(token))
    assert no_tts.status_code == 503

    api.state.tts = tts = ScriptedTts()
    listen = await api.client.get("/v1/studio/reference", params=params, headers=api.bearer(token))
    assert listen.status_code == 200 and listen.content[:4] == b"RIFF"
    assert tts.spoken == [line]
    missing = await api.client.get(
        "/v1/studio/reference", params={**params, "line": "Bonjour."}, headers=api.bearer(token)
    )
    assert missing.status_code == 404

    _attach(api, LexiconRecognizer(LexiconG2P(api.settings.content_root), line, "fr"))
    form = {"line": line, "language": "fr", "attempt": "1"}
    scored = await api.client.post(
        "/v1/studio/shadow", data=form, files={"audio": ("a.wav", _wav(), "audio/wav")}, headers=api.bearer(token)
    )
    assert scored.status_code == 200, scored.text
    assert scored.json()["pitch"]["reference"], "the narrator render is sent as the intonation reference"
    assert scored.json()["intonation"] is not None


class FakeSpeechToSpeech:
    """Records which cloned voice it was asked for; returns the audio unchanged."""

    name = "fake-sts"

    def __init__(self) -> None:
        self.profiles: list[str] = []

    async def convert(self, source_pcm: bytes, target_profile_id: str) -> bytes:
        self.profiles.append(target_profile_id)
        return source_pcm


async def test_reference_is_the_golden_self_when_the_learner_has_a_clone(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    async with api.state.sessions() as db:
        user = (await db.execute(select(User))).scalar_one()
        db.add(
            VoiceProfile(
                tenant_id=user.tenant_id,
                user_id=user.id,
                provider="elevenlabs",
                provider_profile_id="el-voice-1",
                consent_at=datetime.now(UTC),
            )
        )
        await db.commit()
    api.state.tts = ScriptedTts()
    root = api.settings.content_root
    converter = FakeSpeechToSpeech()
    golden = GoldenSelf(None, converter, MemoryCache())
    app = create_app(Engines(LexiconG2P(root), golden, None, load_targets(root)))
    api.state.pronunciation = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pron")

    params = {"line": "Un pain, pas un bain.", "language": "fr"}
    response = await api.client.get("/v1/studio/reference", params=params, headers=api.bearer(token))
    assert response.status_code == 200
    assert converter.profiles == ["el-voice-1"]
    assert watermark.detect(wav_to_pcm(response.content), f"lingard:{user.id}")


async def _say(api, token, text: str, drill: str, stage: int, swap: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    _attach(api, LexiconRecognizer(LexiconG2P(api.settings.content_root), text, "fr", swap=swap))
    form = {"line": text, "language": "fr", "drill": drill, "stage": str(stage)}
    response = await api.client.post(
        "/v1/studio/shadow", data=form, files={"audio": ("a.wav", _wav(), "audio/wav")}, headers=api.bearer(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_drill_is_climbed_stage_by_stage_and_reviewed(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    await api.client.patch("/v1/me", json={"ui_locale": "en"}, headers=api.bearer(token))
    key = "fr.pron.u_vs_ou"
    gym = (await api.client.get("/v1/studio/gym", params={"language": "fr"}, headers=api.bearer(token))).json()
    assert len(gym["drills"]) >= 20 and gym["workout"], "every sound of the language, and a workout to start with"
    view = (await api.client.get(f"/v1/studio/gym/{key}", params={"language": "fr"}, headers=api.bearer(token))).json()
    assert view["stage"] == 0 and [g["phoneme"] for g in view["guides"]] == ["y", "u"]
    assert view["guides"][0]["how"]["steps"] and "u" in view["guides"][0]["confusions"]
    rue = next(w for w in view["words"] if w["text"] == "rue")
    assert rue["words"][0]["phonemes"] == ["ʁ", "y"] and rue["words"][0]["targets"] == [1], (
        "the trained sound is marked"
    )

    async def step(stage: int, score: float | None = None) -> dict[str, Any]:
        body = {"language": "fr", "stage": stage, "score": score}
        answer: dict[str, Any] = (
            await api.client.post(f"/v1/studio/gym/{key}/step", json=body, headers=api.bearer(token))
        ).json()
        return answer

    assert (await step(0))["progress"]["stage"] == 1, "learned: on to listening"
    assert not (await step(1, 0.5))["passed"], "half the pairs heard right is not enough"
    assert (await step(1, 0.875))["progress"]["stage"] == 2

    wrong = await _say(api, token, "rue", key, 2, swap={"y": "u"})
    assert not wrong["good"] and wrong["progress"]["passed_items"] == []
    [tip] = [t for t in wrong["tips"] if t["phoneme"] == "y"]
    assert tip["heard_as"] == "u" and "tongue slid back" in tip["text"], "the fix for exactly what was heard"
    for word in view["words"][:5]:
        said = await _say(api, token, word["text"], key, 2)
    assert said["progress"]["stage"] == 3, "five words said well: on to the pairs"
    for a, b in view["pairs"][:3]:
        said = await _say(api, token, f"{a} / {b}", key, 3)
    assert said["progress"]["stage"] == 4
    for phrase in view["phrases"][:3]:
        said = await _say(api, token, phrase["text"], key, 4)
    assert said["progress"]["stage"] == 5
    said = await _say(api, token, view["sentence"]["text"], key, 5)
    assert said["progress"]["mastered"]

    gym = (await api.client.get("/v1/studio/gym", params={"language": "fr"}, headers=api.bearer(token))).json()
    climbed = next(d for d in gym["drills"] if d["key"] == key)
    assert climbed["mastered"] and climbed["due"] and not climbed["review_due"], "first review in a few days"
    assert gym["sounds"]["y"] > 0
    review = {"language": "fr", "held": False}
    slipped = (await api.client.post(f"/v1/studio/gym/{key}/review", json=review, headers=api.bearer(token))).json()
    assert slipped["stage"] == 2, "a sound that slipped is rebuilt from its words"


async def test_a_model_the_scorer_would_fail_is_left_out_of_its_drill(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_api.routes.studio import CHECKED, check_model

    token = await api.admin_token("Founder", PIN)
    api.state.tts = ScriptedTts()
    g2p = LexiconG2P(api.settings.content_root)
    _attach(api, LexiconRecognizer(g2p, "roue", "fr"))
    assert await check_model(api.state, "roue", "fr") == "narrator", "a model the scorer passes is the narrator's"
    _attach(api, LexiconRecognizer(g2p, "vous", "fr", before=["ə"]))
    assert await check_model(api.state, "vous", "fr") == "none", "an “euh” before the word: every take refused"
    assert len(api.state.tts.spoken) == 1 + 3, "a fresh narrator take each time, before giving up on the text"
    _attach(api, LexiconRecognizer(g2p, "rue", "fr", swap={"y": "u"}))
    assert await check_model(api.state, "rue", "fr") == "none", "heard as roue, and no other native voice to try here"
    CHECKED.clear()  # read back from the object store, as a fresh process would
    view = (
        await api.client.get("/v1/studio/gym/fr.pron.u_vs_ou", params={"language": "fr"}, headers=api.bearer(token))
    ).json()
    words = [w["text"] for w in view["words"]]
    assert "rue" not in words and "roue" in words, "never taught with a model that would teach the mistake"
    CHECKED.clear()


async def test_a_model_can_be_replaced_without_the_device_keeping_the_old_one(api) -> None:  # type: ignore[no-untyped-def]
    token = await api.admin_token("Founder", PIN)
    api.state.tts = ScriptedTts()
    params = {"line": "Un pain, pas un bain.", "language": "fr"}
    first = await api.client.get("/v1/studio/reference", params=params, headers=api.bearer(token))
    assert first.headers["cache-control"] == "private, no-cache" and first.headers["etag"]
    again = await api.client.get(
        "/v1/studio/reference", params=params, headers={**api.bearer(token), "If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304, "the same recording: not sent again"
