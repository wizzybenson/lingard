import base64
from pathlib import Path

import httpx
import numpy as np

from lingard_pronunciation.app import Engines, create_app
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.scoring import PronTarget

from .test_pronunciation import Recognizer, glide

ROOT = Path(__file__).resolve().parents[3]


class FrenchRecognizer(Recognizer):
    inventory = ["<b>", "p", "b", "ɛ̃", "y", "u"]

    def log_posteriors(self, pcm: bytes) -> np.ndarray:
        from .test_pronunciation import posteriors

        return posteriors([2, 3], self.confusions)  # learner says "bain" for "pain"


async def test_shadow_endpoint_scores_against_lexicon_and_flags_critical_target() -> None:
    engines = Engines(
        g2p=LexiconG2P(ROOT / "content"),
        golden=None,
        recognizer=FrenchRecognizer({}),
        targets={"fr": [PronTarget("fr.pron.p_vs_b", ("p", "b"), 0.8, {})]},
    )
    app = create_app(engines)
    payload = {
        "text": "pain",
        "language": "fr",
        "learner_pcm_b64": base64.b64encode(glide(150, 170, 600)).decode(),
        "reference_pcm_b64": base64.b64encode(glide(210, 240, 600)).decode(),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://p") as client:
        response = await client.post("/shadow", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["heatmap"][0]["phoneme"] == "p" and body["heatmap"][0]["heard_as"] == "b"
        assert body["critical"] == ["fr.pron.p_vs_b"]
        unknown = await client.post("/shadow", json={**payload, "text": "anticonstitutionnellement"})
        assert unknown.status_code == 422
        assert (
            await client.post("/golden", json={"text": "x", "accent": "fr-FR", "profile_id": "p", "user_id": "u"})
        ).status_code == 503


async def test_shadow_without_reference_skips_intonation() -> None:
    engines = Engines(g2p=LexiconG2P(ROOT / "content"), golden=None, recognizer=FrenchRecognizer({}), targets={})
    payload = {"text": "pain", "language": "fr", "learner_pcm_b64": base64.b64encode(glide(150, 170, 600)).decode()}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(engines)), base_url="http://p") as c:
        body = (await c.post("/shadow", json=payload)).json()
    assert body["pitch"]["reference"] == [] and body["pitch"]["learner"]


def test_studio_lines_are_in_the_lexicon_and_drill_real_nodes() -> None:
    import yaml

    from lingard_pronunciation.server import load_targets

    g2p, targets = LexiconG2P(ROOT / "content"), load_targets(ROOT / "content")
    for language in ("fr", "en"):
        data = yaml.safe_load((ROOT / "content" / "pronunciation" / f"studio_{language}.yaml").read_text())
        keys = {t.node_key for t in targets[language]}
        for item in data["lines"]:
            assert item["node_key"] in keys, item
            assert g2p.phonemes(item["line"], language), item  # raises KeyError on any word missing from the lexicon
