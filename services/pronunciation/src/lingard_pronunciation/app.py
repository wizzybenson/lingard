"""Pronunciation service HTTP API (internal): golden-self renders and shadowing scores for the Accent Studio."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from lingard_pronunciation.accent import analyse
from lingard_pronunciation.calibration import Calibration
from lingard_pronunciation.g2p import G2P
from lingard_pronunciation.golden_self import GoldenSelf
from lingard_pronunciation.gop import PhonemeScore, score_phonemes
from lingard_pronunciation.prosody import contour_similarity, semitone_contour, to_float, yin_f0
from lingard_pronunciation.recognizer import PhonemeRecognizer
from lingard_pronunciation.scoring import PronTarget, report


@dataclass
class Engines:
    g2p: G2P
    golden: GoldenSelf | None
    recognizer: PhonemeRecognizer | None
    """The recogniser for any language without its own."""
    targets: dict[str, list[PronTarget]]
    """Pronunciation curriculum targets per language (from reviewed ``pron`` nodes)."""
    recognizers: dict[str, PhonemeRecognizer] = field(default_factory=dict)
    """Per language, the recogniser that hears it best (``content/pronunciation/recognizers.yaml``)."""
    calibrations: dict[str, Calibration] = field(default_factory=dict)

    def recognizer_for(self, language: str) -> PhonemeRecognizer | None:
        return self.recognizers.get(language, self.recognizer)


class GoldenRequest(BaseModel):
    text: str
    accent: str
    profile_id: str
    user_id: str
    native_pcm_b64: str | None = None
    """Native-speaker render of ``text``; the caller usually has the TTS, so the service needs none of its own."""


class ShadowRequest(BaseModel):
    text: str
    language: str
    learner_pcm_b64: str
    reference_pcm_b64: str | None = None
    """Golden-self (or native) render of the line. Without it, intonation isn't scored and no pitch overlay is drawn."""
    partners: dict[str, list[str]] | None = None
    """Per sound, the minimal-pair partners it is being trained against: those sounds get the two-way test."""


def by_word(words: list[tuple[str, list[str]]], heatmap: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The heatmap cut back into the written words, each with its mean score, so a line can be coloured word by word."""
    out, start = [], 0
    for text, phonemes in words:
        sounds = heatmap[start : start + len(phonemes)]
        start += len(phonemes)
        score = round(sum(s["score"] for s in sounds) / len(sounds), 1) if sounds else None
        out.append({"text": text, "score": score, "phonemes": sounds})
    return out


def calibrated_music(raw: dict[str, Any], parts: list[str], calibration: Calibration | None) -> dict[str, Any]:
    """The language's own parts of the music, scored against how much native speakers differ from each other: a word's
    stress only where natives agree on it, and an intonation whose ending moves the wrong way never passes."""
    music: dict[str, Any] = {"syllables": raw["syllables"]}
    for part in ("stress", "emphasis", "rhythm", "intonation"):
        found = raw.get(part) if part in parts else None
        if found is None:
            music[part] = None
            continue
        found = dict(found)
        if part == "stress" and calibration is not None:
            words = [
                {**w, "expected": calibration.stress_syllable.get(w["word"].casefold(), w["expected"])}
                for w in found["words"]
                if calibration.stress_judged(w["word"])
            ]
            if not words:
                music[part] = None
                continue
            found["words"] = words
            found["score"] = round(100 * sum(w["expected"] == w["yours"] for w in words) / len(words), 1)
        elif calibration is not None:
            found["score"] = round(calibration.music_score(part, float(found["score"])), 1)
        if part == "intonation":
            final = found.get("final") or {}
            if final.get("expected") in ("rise", "fall") and final.get("yours") != final.get("expected"):
                found["score"] = min(float(found["score"]), 50.0)
        music[part] = found
    return music


def judged(
    scores: list[PhonemeScore], partners: dict[str, list[str]], calibration: Calibration | None
) -> list[PhonemeScore]:
    """A trained sound is also put to the two-way test against its partners (was this "u" or "ou"?), and is marked
    wrong only when that test and its native-calibrated score both say so. Measured on native French (255 takes each
    way): either test alone passes 82% of native speech; requiring both to fail passes 90% and still catches 88% of
    partner substitutions, so a learner who said it right is rarely told otherwise. A contrast this recogniser can't
    separate reliably is marked unchecked, to be compared by ear rather than scored as wrong."""
    out = []
    for s in scores:
        verdicts = [
            (v, partner)
            for partner in partners.get(s.phoneme, [])
            if calibration is not None
            and s.contrast is not None
            and (v := calibration.contrast_score(s.phoneme, partner, s.contrast)) is not None
        ]
        if not verdicts:
            out.append(s)
            continue
        # The partner it sounded like: the one the recogniser heard if it is a partner, else the one it was closest to.
        named = [v for v in verdicts if v[1] == s.likely_substitute]
        (contrast, reliable), partner = named[0] if named else min(verdicts, key=lambda x: x[0][0])
        # A contrast this test separates 90%+ of the time both ways decides alone; otherwise either test may pass it.
        score = (
            contrast if calibration is not None and calibration.strong(s.phoneme, partner) else max(contrast, s.score)
        )
        heard = partner if score < 70 else None
        out.append(
            replace(
                s,
                score=score,
                likely_substitute=heard or (s.likely_substitute if score < 70 else None),
                checked=reliable,
            )
        )
    return out


def create_app(engines: Engines) -> FastAPI:
    app = FastAPI(title="Lingard pronunciation", version="1")

    @app.post("/golden")
    async def golden(body: GoldenRequest) -> dict[str, Any]:
        if engines.golden is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "voice conversion is not configured")
        native = base64.b64decode(body.native_pcm_b64) if body.native_pcm_b64 else None
        try:
            render = await engines.golden.render(
                body.text, accent=body.accent, profile_id=body.profile_id, user_id=body.user_id, native=native
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        return {
            "pcm_b64": base64.b64encode(render.pcm).decode(),
            "cache_key": render.cache_key,
            "cached": render.cached,
        }

    @app.post("/shadow")
    async def shadow(body: ShadowRequest) -> dict[str, Any]:
        recognizer = engines.recognizer_for(body.language)
        if recognizer is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "phoneme recogniser is not installed")
        calibration = engines.calibrations.get(body.language)
        try:
            words = engines.g2p.words(body.text, body.language)
            expected = [p for _, phonemes in words for p in phonemes]
        except KeyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        learner = base64.b64decode(body.learner_pcm_b64)

        def scored(pcm: bytes) -> list[PhonemeScore]:
            assert recognizer is not None
            return score_phonemes(
                recognizer.log_posteriors(pcm),
                expected,
                recognizer.inventory,
                engines.g2p.variants(body.language),
                engines.g2p.competitors(body.language),
                calibration.scale if calibration else None,
                body.partners,
            )

        scores = judged(scored(learner), body.partners or {}, calibration)
        reference_pcm = base64.b64decode(body.reference_pcm_b64) if body.reference_pcm_b64 else None
        music = None
        if reference_pcm is not None:
            try:
                vowels = engines.g2p.vowels(body.language)
                raw = analyse(learner, scores, reference_pcm, scored(reference_pcm), words, vowels)
                music = calibrated_music(raw, engines.g2p.music(body.language), calibration)
            except ValueError:  # a reference too short to align: the sounds are still scored
                music = None
        learner_f0 = yin_f0(to_float(learner))
        reference_f0 = yin_f0(to_float(reference_pcm)) if reference_pcm is not None else None
        intonation = contour_similarity(learner_f0, reference_f0) if reference_f0 is not None else None
        result = report(scores, engines.targets.get(body.language, []), intonation=intonation)
        return {
            "intelligibility": round(result.intelligibility, 1),
            "accent_proximity": round(result.accent_proximity, 1),
            "intonation": round(intonation, 1) if intonation is not None else None,
            "node_scores": result.node_scores,
            "critical": result.critical,
            "heatmap": [
                {**entry, "checked": s.checked, "contrast": s.contrast}
                for entry, s in zip(result.heatmap, scores, strict=True)
            ],
            "prosody": music,
            "words": by_word(
                words,
                [{**e, "checked": s.checked} for e, s in zip(result.heatmap, scores, strict=True)],
            ),
            "pitch": {
                "learner": semitone_contour(learner_f0).round(2).tolist(),
                "reference": semitone_contour(reference_f0).round(2).tolist() if reference_f0 is not None else [],
            },
        }

    return app
