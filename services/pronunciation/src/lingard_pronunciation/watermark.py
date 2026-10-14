"""Inaudible spread-spectrum watermark for synthesised audio in a learner's voice (SPEC §23.1).

A keyed ±1 pseudo-random sequence at low amplitude is added to the samples; detection correlates against the same
key. Basic by design: it marks provenance of our own renders and survives mild gain changes, not adversarial removal.
"""

from __future__ import annotations

import hashlib

import numpy as np

AMPLITUDE = 0.002  # relative to full scale (about −54 dBFS)
THRESHOLD = 6.0  # z-score for a positive detection


def _sequence(key: str, length: int) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    return np.random.default_rng(seed).choice([-1.0, 1.0], size=length)


def embed(pcm: bytes, key: str) -> bytes:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    marked = samples + AMPLITUDE * 32767 * _sequence(key, samples.size)
    return np.clip(marked, -32768, 32767).astype(np.int16).tobytes()


def detect(pcm: bytes, key: str) -> bool:
    """Pearson correlation of first differences (suppresses speech energy, which is mostly low-frequency) → z-score."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    if samples.size < 1600:
        return False
    signal, sequence = np.diff(samples), np.diff(_sequence(key, samples.size))
    if float(np.std(signal)) == 0.0:
        return False
    correlation = float(np.corrcoef(signal, sequence)[0, 1])
    return bool(correlation * np.sqrt(signal.size) > THRESHOLD)
