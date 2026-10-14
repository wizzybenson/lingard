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
from fastapi import FastAPI

from lingard_pronunciation.app import Engines, create_app
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.golden_self import ElevenLabsSpeechToSpeech, GoldenSelf, MemoryCache
from lingard_pronunciation.recognizer import PhonemeRecognizer, Wav2Vec2PhonemeRecognizer
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


def _recognizer() -> PhonemeRecognizer | None:
    if os.environ.get("LINGARD_PRON_RECOGNIZER", "auto") == "off":
        return None
    try:
        return Wav2Vec2PhonemeRecognizer(os.environ.get("LINGARD_PRON_MODEL", "facebook/wav2vec2-lv-60-espeak-cv-ft"))
    except RuntimeError as exc:
        logger.warning("pronunciation scoring disabled: %s", exc)
        return None


def _golden() -> GoldenSelf | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    return GoldenSelf(None, ElevenLabsSpeechToSpeech(key), MemoryCache()) if key else None


def build_app(content_root: Path | None = None) -> FastAPI:
    root = content_root or Path(os.environ.get("LINGARD_CONTENT_ROOT", REPO_ROOT / "content"))
    return create_app(
        Engines(g2p=LexiconG2P(root), golden=_golden(), recognizer=_recognizer(), targets=load_targets(root))
    )
