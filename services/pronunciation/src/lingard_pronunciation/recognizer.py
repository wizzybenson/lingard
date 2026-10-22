"""Phoneme recogniser seam. The production adapter (wav2vec2 phoneme CTC, Apache-2.0) is an optional install."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import numpy as np
import yaml
from numpy.typing import NDArray

PAD_S = 0.3


class PhonemeRecognizer(Protocol):
    inventory: list[str]
    """Symbol per output column; index 0 is the CTC blank."""

    def log_posteriors(self, pcm: bytes) -> NDArray[np.float64]: ...


class Wav2Vec2PhonemeRecognizer:
    """wav2vec2 CTC phoneme models (``facebook/wav2vec2-lv-60-espeak-cv-ft``, ``bofenghuang/phonemizer-wav2vec2-ctc-
    french``…). Needs ``transformers`` and ``torch`` (``pip install lingard-pronunciation[models]``). Columns are
    reordered so the CTC blank comes first, and a word separator ("|"), which these models emit between words, is
    folded into the blank: a pause between words is not a sound to score."""

    def __init__(self, model_name: str = "facebook/wav2vec2-lv-60-espeak-cv-ft") -> None:
        try:
            import torch
            from transformers import AutoModelForCTC, Wav2Vec2CTCTokenizer, Wav2Vec2FeatureExtractor
        except ImportError as exc:
            raise RuntimeError("install lingard-pronunciation[models] for the wav2vec2 recogniser") from exc
        self._torch = torch
        try:
            tokenizer = Wav2Vec2CTCTokenizer.from_pretrained(model_name)  # type: ignore[no-untyped-call,unused-ignore]
            self._features = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
            self._model = AutoModelForCTC.from_pretrained(model_name).eval()
        except (ImportError, OSError) as exc:  # the phoneme tokenizer needs phonemizer + espeak-ng; or no model files
            raise RuntimeError(f"wav2vec2 recogniser unavailable: {exc}") from exc
        vocab: dict[str, int] = tokenizer.get_vocab()
        blank = int(tokenizer.pad_token_id)
        width = self._width()
        # Only a separator the model actually outputs (lv-60's tokenizer lists "|" past the model's last column).
        separator = vocab["|"] if "|" in vocab and vocab["|"] != blank and vocab["|"] < width else None
        others = sorted((i, t) for t, i in vocab.items() if i not in (blank, separator) and i < width)
        self._order = [blank, *(i for i, _ in others)]
        self._separator = separator
        self.inventory = [tokenizer.pad_token, *(t for _, t in others)]
        self.model_name = model_name

    def _width(self) -> int:
        return int(self._model.config.vocab_size)

    def log_posteriors(self, pcm: bytes) -> NDArray[np.float64]:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        # A single word can be a quarter of a second, too few frames for the model to hear anything; silence around it
        # gives it room (2026-10-22: a short "rue" decoded as nothing, padded as "t ʁ i").
        silence = np.zeros(int(16_000 * PAD_S), dtype=np.float32)
        audio = np.concatenate([silence, audio, silence])
        inputs = self._features(audio, sampling_rate=16_000, return_tensors="pt")
        with self._torch.no_grad():
            logits = self._model(inputs.input_values).logits[0]
        logp = np.asarray(self._torch.log_softmax(logits, dim=-1).numpy(), dtype=np.float64)
        if self._separator is not None:
            logp[:, self._order[0]] = np.logaddexp(logp[:, self._order[0]], logp[:, self._separator])
        return logp[:, self._order]


def load_recognizers(content_root: Path, models: Mapping[str, str] | None = None) -> dict[str, PhonemeRecognizer]:
    """The recogniser of each language (``content/pronunciation/recognizers.yaml``); one model serves languages that
    share it. ``models`` overrides the file (language → model name)."""
    chosen = models or {
        lang: str(entry["model"])
        for lang, entry in yaml.safe_load((content_root / "pronunciation" / "recognizers.yaml").read_text()).items()
    }
    loaded: dict[str, PhonemeRecognizer] = {}
    out: dict[str, PhonemeRecognizer] = {}
    for language, name in chosen.items():
        if name not in loaded:
            loaded[name] = Wav2Vec2PhonemeRecognizer(name)
        out[language] = loaded[name]
    return out
