"""Pronunciation service HTTP API (internal): golden-self renders and shadowing scores for the Accent Studio."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from lingard_pronunciation.g2p import G2P
from lingard_pronunciation.golden_self import GoldenSelf
from lingard_pronunciation.gop import score_phonemes
from lingard_pronunciation.prosody import contour_similarity, semitone_contour, to_float, yin_f0
from lingard_pronunciation.recognizer import PhonemeRecognizer
from lingard_pronunciation.scoring import PronTarget, report


@dataclass
class Engines:
    g2p: G2P
    golden: GoldenSelf | None
    recognizer: PhonemeRecognizer | None
    targets: dict[str, list[PronTarget]]
    """Pronunciation curriculum targets per language (from reviewed ``pron`` nodes)."""


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
        if engines.recognizer is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "phoneme recogniser is not installed")
        try:
            expected = engines.g2p.phonemes(body.text, body.language)
        except KeyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        learner = base64.b64decode(body.learner_pcm_b64)
        scores = score_phonemes(engines.recognizer.log_posteriors(learner), expected, engines.recognizer.inventory)
        learner_f0 = yin_f0(to_float(learner))
        reference_f0 = yin_f0(to_float(base64.b64decode(body.reference_pcm_b64))) if body.reference_pcm_b64 else None
        intonation = contour_similarity(learner_f0, reference_f0) if reference_f0 is not None else None
        result = report(scores, engines.targets.get(body.language, []), intonation=intonation)
        return {
            "intelligibility": round(result.intelligibility, 1),
            "accent_proximity": round(result.accent_proximity, 1),
            "intonation": round(intonation, 1) if intonation is not None else None,
            "node_scores": result.node_scores,
            "critical": result.critical,
            "heatmap": result.heatmap,
            "pitch": {
                "learner": semitone_contour(learner_f0).round(2).tolist(),
                "reference": semitone_contour(reference_f0).round(2).tolist() if reference_f0 is not None else [],
            },
        }

    return app
