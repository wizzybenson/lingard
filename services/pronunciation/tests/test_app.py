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
        [word] = body["words"]
        assert word["text"] == "pain" and [p["phoneme"] for p in word["phonemes"]] == ["p", "ɛ̃"]
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


def test_phrases_keep_liaison_and_their_word_boundaries() -> None:
    g2p = LexiconG2P(ROOT / "content")
    assert g2p.words("Les amis", "fr") == [("Les", ["l", "e", "z"]), ("amis", ["a", "m", "i"])]


def test_sounds_heard_beyond_the_words_own_are_extra_and_a_misheard_one_is_not() -> None:
    from lingard_pronunciation.app import extra_sounds, spelled
    from lingard_pronunciation.recognizer import Heard

    def heard(*phonemes: str) -> list[Heard]:
        return [Heard(p, i * 0.1, i * 0.1 + 0.08) for i, p in enumerate(phonemes)]

    filler = extra_sounds(heard("a", "ʁ", "y"), ["ʁ", "y"])
    assert filler["before"] == ["a"] and filler["after"] == [] and filler["start"] == 0.1, "a filler ahead of rue"
    tail = extra_sounds(heard("ʁ", "u", "ə"), ["ʁ", "u"])
    assert tail["after"] == ["ə"], "a sound trailing after the word"
    assert extra_sounds(heard("ʁ", "w", "e"), ["ʁ", "u"])["after"] == ["e"], "in a tie, extra rather than misheard"
    assert extra_sounds(heard("ə", "ʁ", "y", "a"), ["ʁ", "y"])["before"] == ["ə"], "both ends at once"
    assert extra_sounds([], ["ʁ", "y"])["start"] is None
    tilde = "\u0303"
    bain = spelled(["b", f"ɛ{tilde}"], ["<b>", "b", "ɛ", tilde, "n"])
    assert bain == ["b", "ɛ", tilde], "a nasal vowel written as the recogniser writes it: vowel + tilde"
    assert extra_sounds(heard("b", "ɛ", tilde), bain)["after"] == []
    assert extra_sounds(heard("b", "ɛ", "ɛ", "n"), bain)["after"] == [], "its nasality heard as an n is the vowel"
    assert extra_sounds(heard("b", "ɛ", tilde, "n", "a"), bain)["after"] == ["a"], "a syllable beyond it is not"
    assert extra_sounds(heard("s", "u"), ["s", "y"]) == {"before": [], "after": [], "start": 0.0, "end": 0.18}, (
        "su heard as sou is a mispronunciation for the scorer to judge, not an extra sound"
    )
