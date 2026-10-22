"""Calibrate Accent Studio scoring against native speech (decision 0028).

The phoneme recogniser is multilingual and off the shelf, so its raw goodness-of-pronunciation (GOP) differs by sound:
it calls a native French /ʁ/ "r" with near certainty. Two measurements make its scores honest:

1. Native baseline: every studio text is rendered by several native voices and scored. For each sound, the 10th and
   50th percentile GOP of native speech become the scale: as good as most native speakers scores high.
2. Contrasts: each minimal pair's partner word (native "roue" where "rue" is expected) is scored against the target.
   The share of those substitutions the calibrated score catches is the contrast's detection rate. A sound whose
   contrasts are not caught reliably is marked unchecked: the studio asks the learner to compare by ear instead of
   pretending to judge it.

Writes ``content/pronunciation/calibration_<lang>.yaml``. Paid (OpenAI text-to-speech, well under a dollar per
language); the audio is cached under ``~/.cache/lingard/calibration`` and never committed.

    uv run --all-packages --extra models python -m tools.content_cli.calibrate fr [en]
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import yaml
from dotenv import load_dotenv

from lingard_live.audio import resample
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.gop import calibrated_score, score_phonemes
from lingard_pronunciation.gym import load_gym
from lingard_pronunciation.recognizer import load_recognizers
from tools.content_cli.lexicon import texts

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / ".cache" / "lingard" / "calibration"
MODEL = "gpt-4o-mini-tts"
VOICES = ("alloy", "nova", "onyx")
STYLE = {
    "fr": "Speak standard Metropolitan French, clearly, at a natural conversational pace.",
    "en": "Speak standard Southern British English (RP), clearly, at a natural conversational pace.",
}
DETECTED = 0.8
"""A contrast whose native targets pass, and whose substitutions are caught, at least this often may be judged."""


async def render(client: httpx.AsyncClient, text: str, voice: str, language: str, gate: asyncio.Semaphore) -> bytes:
    path = CACHE / language / voice / f"{hashlib.sha256(text.encode()).hexdigest()[:20]}.pcm"
    if path.exists():
        return path.read_bytes()
    body = {"model": MODEL, "voice": voice, "input": text, "instructions": STYLE[language], "response_format": "pcm"}
    async with gate:
        response = await client.post("https://api.openai.com/v1/audio/speech", json=body)
    response.raise_for_status()
    pcm = resample(response.content, 24_000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm)
    return pcm


def differing(a: list[str], b: list[str]) -> list[int]:
    """Positions where two same-length transcriptions differ (a minimal pair differs in one or two)."""
    return [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y] if len(a) == len(b) else []


def cached(language: str, source: str, text: str) -> bytes | None:
    path = CACHE / language / source / f"{hashlib.sha256(text.encode()).hexdigest()[:20]}.pcm"
    return path.read_bytes() if path.exists() else None


async def calibrate(language: str) -> dict[str, object]:
    g2p = LexiconG2P(ROOT / "content")
    recognizer = load_recognizers(ROOT / "content")[language]
    variants, competitors = g2p.variants(language), g2p.competitors(language)
    gym = load_gym(ROOT / "content", language)
    all_texts = texts(language)
    gate = asyncio.Semaphore(6)
    key = os.environ["OPENAI_API_KEY"]
    async with httpx.AsyncClient(timeout=60, headers={"Authorization": f"Bearer {key}"}) as client:
        await asyncio.gather(*(render(client, t, v, language, gate) for t in all_texts for v in VOICES))
    sources = [*VOICES, "elevenlabs"]  # the narrator the learner hears, wherever its renders are cached
    audio = {(t, s): pcm for t in all_texts for s in sources if (pcm := cached(language, s, t)) is not None}
    posteriors: dict[tuple[str, str], np.ndarray] = {}

    def scores(source_text: str, source: str, as_text: str, partners: dict[str, list[str]] | None = None) -> list:  # type: ignore[type-arg]
        if (source_text, source) not in posteriors:
            posteriors[(source_text, source)] = recognizer.log_posteriors(audio[(source_text, source)])
        expected = g2p.phonemes(as_text, language)
        return score_phonemes(
            posteriors[(source_text, source)], expected, recognizer.inventory, variants, competitors, None, partners
        )

    native: dict[str, list[float]] = defaultdict(list)
    for text, source in audio:
        for phoneme, s in zip(g2p.phonemes(text, language), scores(text, source, text), strict=True):
            native[phoneme].append(s.gop)
    scale = {
        p: {"p10": round(float(np.percentile(v, 10)), 3), "p50": round(float(np.percentile(v, 50)), 3), "n": len(v)}
        for p, v in sorted(native.items())
    }

    # The two-way test, measured both ways for every minimal pair: native targets, and the partner said instead.
    said_right: dict[tuple[str, str], list[float]] = defaultdict(list)
    said_wrong: dict[tuple[str, str], list[float]] = defaultdict(list)
    for drill in gym.drills:
        for a, b in drill.pairs:
            for target, partner in ((a, b), (b, a)):
                expected, other = g2p.phonemes(target, language), g2p.phonemes(partner, language)
                diff = differing(expected, other)
                if len(diff) != 1:
                    continue
                i = diff[0]
                pair = {expected[i]: [other[i]]}
                for source in sources:
                    if (target, source) in audio:
                        value = scores(target, source, target, pair)[i].contrast
                        if value is not None:
                            said_right[(expected[i], other[i])].append(value)
                    if (partner, source) in audio:
                        value = scores(partner, source, target, pair)[i].contrast
                        if value is not None:
                            said_wrong[(expected[i], other[i])].append(value)
    contrasts = {}
    for (want, got), right in sorted(said_right.items()):
        wrong = said_wrong.get((want, got), [])
        if len(right) < 3 or len(wrong) < 3:
            continue
        native_edge, error_edge = float(np.percentile(right, 10)), float(np.percentile(wrong, 90))
        threshold = (native_edge + error_edge) / 2
        passed = float(np.mean(np.array(right) > threshold))
        caught = float(np.mean(np.array(wrong) <= threshold))
        contrasts[f"{want} {got}"] = {
            "threshold": round(threshold, 3),
            "width": round(max((native_edge - error_edge) / 2, 0.5), 3),
            "native_pass": round(passed, 2),
            "caught": round(caught, 2),
            "reliable": bool(passed >= DETECTED and caught >= DETECTED),
            "n": [len(right), len(wrong)],
        }
    native_ok = {
        p: round(sum(calibrated_score(v, scale[p]["p10"], scale[p]["p50"]) >= 70 for v in values) / len(values), 2)
        for p, values in native.items()
    }
    return {
        "model": recognizer.model_name,  # type: ignore[attr-defined]
        "voices": [f"openai {MODEL} {v}" for v in VOICES] + ["elevenlabs narrator (words)"],
        "as_of": date.today().isoformat(),
        "texts": len(all_texts),
        "scale": scale,
        "native_pass_rate": dict(sorted(native_ok.items())),
        "contrasts": contrasts,
        "unreliable": sorted(k for k, c in contrasts.items() if not c["reliable"]),
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    for language in sys.argv[1:] or ["fr", "en"]:
        result = asyncio.run(calibrate(language))
        header = (
            f"# Accent Studio calibration ({language}), generated by tools/content_cli/calibrate.py; do not edit.\n"
            "# scale: native GOP percentiles per sound. contrasts: the two-way test's threshold, native pass rate and\n"
            "# share of partner substitutions caught.\n"
            "# unreliable: contrasts this recogniser does not separate reliably (compared by ear instead of scored).\n"
        )
        path = ROOT / "content" / "pronunciation" / f"calibration_{language}.yaml"
        path.write_text(header + yaml.safe_dump(result, allow_unicode=True, sort_keys=False, width=1000))
        rates = result["native_pass_rate"]
        assert isinstance(rates, dict)
        print(f"{language}: {result['texts']} texts; contrasts not reliable: {result['unreliable']}")
        print(f"  native sounds passing: {np.mean(list(rates.values())):.0%} on average")


if __name__ == "__main__":
    main()
