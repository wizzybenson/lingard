"""Phoneme recogniser seam. The production adapter (wav2vec2 phoneme CTC, Apache-2.0) is an optional install."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class PhonemeRecognizer(Protocol):
    inventory: list[str]
    """Symbol per output column; index 0 is the CTC blank."""

    def log_posteriors(self, pcm: bytes) -> NDArray[np.float64]: ...


class Wav2Vec2PhonemeRecognizer:
    """``facebook/wav2vec2-lv-60-espeak-cv-ft`` style models (multilingual IPA phonemes). Needs ``transformers`` and
    ``torch`` (``pip install lingard-pronunciation[models]``); L2-tuned checkpoints per language replace it later."""

    def __init__(self, model_name: str = "facebook/wav2vec2-lv-60-espeak-cv-ft") -> None:
        try:
            import torch
            from transformers import AutoModelForCTC, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("install lingard-pronunciation[models] for the wav2vec2 recogniser") from exc
        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(model_name)
        self._model = AutoModelForCTC.from_pretrained(model_name).eval()
        vocab = self._processor.tokenizer.get_vocab()
        self.inventory = [token for token, _ in sorted(vocab.items(), key=lambda kv: kv[1])]

    def log_posteriors(self, pcm: bytes) -> NDArray[np.float64]:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        inputs = self._processor(audio, sampling_rate=16_000, return_tensors="pt")
        with self._torch.no_grad():
            logits = self._model(inputs.input_values).logits[0]
        return np.asarray(self._torch.log_softmax(logits, dim=-1).numpy(), dtype=np.float64)
