import math

import httpx
import numpy as np
from sqlalchemy import select

from lingard_db.models import User
from lingard_live.audio import pcm_to_wav
from lingard_pronunciation.app import Engines, create_app
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.server import load_targets

PIN = "613470"


class LexiconRecognizer:
    """Hears exactly the expected phonemes, except one swap (to simulate an accent)."""

    def __init__(self, g2p: LexiconG2P, line: str, language: str, swap: dict[str, str] | None = None) -> None:
        self.expected = g2p.phonemes(line, language)
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

    _attach(api, LexiconRecognizer(LexiconG2P(api.settings.content_root), line, "fr", swap={"p": "b"}))
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
