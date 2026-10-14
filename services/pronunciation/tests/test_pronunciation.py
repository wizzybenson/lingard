import math

import numpy as np
import pytest

from lingard_pronunciation import watermark
from lingard_pronunciation.clone import FakeClone, create_with_fallback
from lingard_pronunciation.golden_self import GoldenSelf
from lingard_pronunciation.gop import align, score_phonemes
from lingard_pronunciation.prosody import (
    SAMPLE_RATE,
    contour_similarity,
    npvi,
    pauses,
    speech_rate,
    to_float,
    yin_f0,
)
from lingard_pronunciation.scoring import PronTarget, diagnostic_priority, report
from lingard_pronunciation.studio import MAX_ATTEMPTS, StudioItem, shadow

INVENTORY = ["<b>", "p", "b", "a", "y", "u"]


def glide(f_start: float, f_end: float, ms: int, amp: float = 0.3) -> bytes:
    t = np.arange(int(SAMPLE_RATE * ms / 1000)) / SAMPLE_RATE
    freq = np.linspace(f_start, f_end, t.size)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    return (amp * 32767 * np.sin(phase)).astype(np.int16).tobytes()


def silence(ms: int) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * ms / 1000)


def test_yin_tracks_pitch() -> None:
    f0 = yin_f0(to_float(glide(150, 150, 500)))
    voiced = f0[f0 > 0]
    assert voiced.size > 20 and abs(float(np.median(voiced)) - 150) < 3


def test_contour_similarity_rewards_matching_intonation_regardless_of_register() -> None:
    rising_low, rising_high = yin_f0(to_float(glide(110, 165, 600))), yin_f0(to_float(glide(200, 300, 600)))
    falling = yin_f0(to_float(glide(300, 200, 600)))
    assert contour_similarity(rising_low, rising_high) > 80
    assert contour_similarity(rising_low, falling) < contour_similarity(rising_low, rising_high) - 30


def test_pauses_rate_and_rhythm() -> None:
    profile = pauses(to_float(glide(150, 150, 400) + silence(300) + glide(150, 150, 400)))
    assert len(profile.pauses_ms) == 1 and 280 <= profile.pauses_ms[0] <= 320
    assert 8.5 <= speech_rate(7, profile) <= 9.5
    assert npvi([100, 100, 100]) == 0 and npvi([50, 150, 50, 150]) > 90


def posteriors(path: list[int], confusions: dict[int, int] | None = None, frames_per: int = 4) -> np.ndarray:
    """Synthetic CTC log-posteriors following ``path`` (with blanks between), optionally confusing tokens."""
    rows = []
    for token in path:
        heard = (confusions or {}).get(token, token)
        for _ in range(frames_per):
            row = np.full(len(INVENTORY), math.log(0.02))
            row[heard] = math.log(0.85)
            if heard != token:
                row[token] = math.log(0.1)
            rows.append(row)
        blank = np.full(len(INVENTORY), math.log(0.02))
        blank[0] = math.log(0.9)
        rows.append(blank)
    return np.array(rows)


def test_alignment_and_gop_detect_substitution() -> None:
    expected = ["p", "a", "y"]
    clean = score_phonemes(posteriors([1, 3, 4]), expected, INVENTORY)
    assert all(s.score > 80 and s.likely_substitute is None for s in clean)
    confused = score_phonemes(posteriors([1, 3, 4], {1: 2, 4: 5}), expected, INVENTORY)
    assert confused[0].likely_substitute == "b" and confused[0].score < 30
    assert confused[2].likely_substitute == "u"
    assert confused[1].score > 80
    spans = align(posteriors([1, 3, 4]), [1, 3, 4])
    assert spans[0][0] < spans[1][0] < spans[2][0]


def test_two_dials_and_critical_targets() -> None:
    targets = [
        PronTarget("fr.pron.p_vs_b", ("p", "b"), 0.8, {"ar": 0.9, "generic": 0.2}),
        PronTarget("fr.pron.u_vs_ou", ("y", "u"), 0.9, {"ar": 0.9, "generic": 0.6}),
        PronTarget("fr.pron.uvular_r", ("ʁ",), 0.3, {"ar": 0.2, "generic": 0.6}),
    ]
    scores = score_phonemes(posteriors([1, 3, 4], {1: 2}), ["p", "a", "y"], INVENTORY)
    result = report(scores, targets, intonation=90)
    assert result.critical == ["fr.pron.p_vs_b"], "low score on a high-functional-load target is critical"
    assert result.intelligibility < result.accent_proximity + 40
    assert result.heatmap[0]["heard_as"] == "b"
    order = [t.node_key for t in diagnostic_priority(targets, "ar")]
    assert order[0] in {"fr.pron.u_vs_ou", "fr.pron.p_vs_b"} and order[-1] == "fr.pron.uvular_r"


def test_watermark_detectable_only_with_the_right_key() -> None:
    audio = glide(180, 220, 2000)
    marked = watermark.embed(audio, "lingard:user-1")
    assert watermark.detect(marked, "lingard:user-1")
    assert not watermark.detect(marked, "lingard:user-2")
    assert not watermark.detect(audio, "lingard:user-1")
    quieter = (np.frombuffer(marked, dtype=np.int16) * 0.7).astype(np.int16).tobytes()
    assert watermark.detect(quieter, "lingard:user-1")


class Converter:
    name = "fake-vc"

    def __init__(self) -> None:
        self.calls = 0

    async def convert(self, source_pcm: bytes, target_profile_id: str) -> bytes:
        self.calls += 1
        return source_pcm


class Cache:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    async def put(self, key: str, audio: bytes) -> None:
        self.store[key] = audio


async def test_golden_self_converts_watermarks_and_caches() -> None:
    async def native(text: str, accent: str) -> bytes:
        return glide(200, 260, 1500)

    converter, cache = Converter(), Cache()
    golden = GoldenSelf(native, converter, cache)
    first = await golden.render("Bonjour", accent="fr-FR", profile_id="vb-1", user_id="u1")
    again = await golden.render("Bonjour", accent="fr-FR", profile_id="vb-1", user_id="u1")
    assert not first.cached and again.cached and converter.calls == 1
    assert watermark.detect(first.pcm, "lingard:u1")


async def test_clone_fallback_and_idempotent_delete() -> None:
    primary, backup = FakeClone(name="voicebox", fail_create=True), FakeClone(name="elevenlabs")
    provider, profile = await create_with_fallback(primary, backup, "u1", b"\x00\x01" * 100)
    assert provider == "elevenlabs" and await backup.exists(profile)
    await backup.delete(profile)
    await backup.delete(profile)
    assert not await backup.exists(profile)


class Recognizer:
    inventory = INVENTORY

    def __init__(self, confusions: dict[int, int]) -> None:
        self.confusions = confusions

    def log_posteriors(self, pcm: bytes) -> np.ndarray:
        return posteriors([1, 3, 4], self.confusions)


def test_studio_loop_max_three_attempts_and_fsrs_grade() -> None:
    targets = [PronTarget("fr.pron.p_vs_b", ("p", "b"), 0.8, {})]
    item = StudioItem("pain", ["p", "a", "y"], targets, reference_pcm=glide(200, 240, 800))
    shadow(item, glide(150, 180, 800), Recognizer({1: 2, 4: 5}))
    shadow(item, glide(150, 180, 800), Recognizer({1: 2, 4: 5}))
    assert not item.done
    shadow(item, glide(150, 180, 800), Recognizer({}))
    assert item.passed and item.review_grade() == (True, True)
    with pytest.raises(ValueError):
        shadow(item, glide(150, 180, 800), Recognizer({}))
    assert len(item.attempts) == MAX_ATTEMPTS
