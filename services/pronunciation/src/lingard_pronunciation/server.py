"""Runnable pronunciation service: ``uvicorn --factory lingard_pronunciation.server:build_app --port 58100``.

The wav2vec2 recogniser loads only when the ``models`` extra is installed and ``LINGARD_PRON_RECOGNIZER`` is not
``off``; without it ``/shadow`` answers 503 and the API reports scoring as unavailable. Golden-self renders need
``ELEVENLABS_API_KEY`` (speech-to-speech into the learner's cloned voice); without it ``/golden`` answers 503.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI

from lingard_pronunciation.app import Engines, create_app
from lingard_pronunciation.calibration import load_calibration
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.golden_self import ElevenLabsSpeechToSpeech, GoldenSelf, MemoryCache
from lingard_pronunciation.recognizer import PhonemeRecognizer, load_recognizers
from lingard_pronunciation.scoring import PronTarget

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[4]


def load_targets(content_root: Path) -> dict[str, list[PronTarget]]:
    """Pronunciation targets per language, from ``content/curriculum/<lang>/pron.yaml``."""
    targets: dict[str, list[PronTarget]] = {}
    for path in sorted(content_root.glob("curriculum/*/pron.yaml")):
        data: dict[str, Any] = yaml.safe_load(path.read_text())
        language = str(data["defaults"]["language"])
        targets[language] = [PronTarget.from_node(n["key"], n.get("payload", {})) for n in data["nodes"]]
    return targets


def _recognizers(root: Path) -> dict[str, PhonemeRecognizer]:
    """Each language's recogniser (``content/pronunciation/recognizers.yaml``); none when scoring is switched off or the
    models can't load."""
    if os.environ.get("LINGARD_PRON_RECOGNIZER", "auto") == "off":
        return {}
    try:
        return load_recognizers(root)
    except RuntimeError as exc:
        logger.warning("pronunciation scoring disabled: %s", exc)
        return {}


def _golden() -> GoldenSelf | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    model = os.environ.get("ELEVENLABS_STS_MODEL", "eleven_multilingual_sts_v2")
    return GoldenSelf(None, ElevenLabsSpeechToSpeech(key, model), MemoryCache())


def build_app(content_root: Path | None = None) -> FastAPI:
    load_dotenv()
    root = content_root or Path(os.environ.get("LINGARD_CONTENT_ROOT", REPO_ROOT / "content"))
    recognizers = _recognizers(root)
    calibrations = {
        language: calibration
        for language, recognizer in recognizers.items()
        if (calibration := load_calibration(root, language, getattr(recognizer, "model_name", ""))) is not None
    }
    return create_app(
        Engines(
            g2p=LexiconG2P(root),
            golden=_golden(),
            recognizer=None,
            targets=load_targets(root),
            recognizers=recognizers,
            calibrations=calibrations,
        )
    )
