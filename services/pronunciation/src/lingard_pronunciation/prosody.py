"""Prosody features on 16 kHz PCM: F0 (YIN), contour comparison by DTW, speech rate, pauses, rhythm (nPVI)."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE = 16_000
FRAME = 640  # 40 ms analysis window
HOP = 160  # 10 ms hop
F0_MIN, F0_MAX = 60.0, 400.0

Floats = NDArray[np.float64]


def to_float(pcm: bytes) -> Floats:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0


def yin_f0(signal: Floats, threshold: float = 0.15) -> Floats:
    """Per-hop F0 in Hz; 0 for unvoiced frames (de Cheveigné & Kawahara, 2002)."""
    tau_min, tau_max = int(SAMPLE_RATE / F0_MAX), int(SAMPLE_RATE / F0_MIN)
    out = []
    for start in range(0, len(signal) - FRAME - tau_max, HOP):
        frame = signal[start : start + FRAME + tau_max]
        if float(np.sqrt(np.mean(frame[:FRAME] ** 2))) < 0.01:
            out.append(0.0)
            continue
        diff = np.array([np.sum((frame[:FRAME] - frame[tau : tau + FRAME]) ** 2) for tau in range(tau_max)])
        cumulative = np.cumsum(diff[1:])
        cmnd = np.ones_like(diff)
        cmnd[1:] = diff[1:] * np.arange(1, tau_max) / np.where(cumulative == 0, 1, cumulative)
        candidates = np.where(cmnd[tau_min:] < threshold)[0]
        if candidates.size == 0:
            out.append(0.0)
            continue
        tau = candidates[0] + tau_min
        while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
        out.append(SAMPLE_RATE / tau)
    return np.array(out)


def semitone_contour(f0: Floats) -> Floats:
    """Voiced frames only, in semitones relative to the speaker's median (removes the voice's register)."""
    voiced = f0[f0 > 0]
    if voiced.size == 0:
        return np.array([])
    return np.asarray(12 * np.log2(voiced / np.median(voiced)), dtype=np.float64)


def dtw_distance(a: Floats, b: Floats) -> float:
    """Normalised DTW distance between two contours (mean absolute semitone gap along the best path)."""
    if a.size == 0 or b.size == 0:
        return math.inf
    n, m = a.size, b.size
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(max(1, i - max(n, m) // 2), min(m, i + max(n, m) // 2) + 1):
            d = abs(a[i - 1] - b[j - 1])
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    return float(cost[n, m] / (n + m))


def contour_similarity(learner: Floats, reference: Floats) -> float:
    """0–100: 100 = intonation shape matches the reference (the learner's golden self)."""
    distance = dtw_distance(semitone_contour(learner), semitone_contour(reference))
    return 0.0 if math.isinf(distance) else float(100 * math.exp(-distance / 2.0))


@dataclass(frozen=True)
class PauseProfile:
    pauses_ms: list[int]
    speech_ms: int


def pauses(signal: Floats, min_pause_ms: int = 150) -> PauseProfile:
    frame = SAMPLE_RATE // 100
    energies = [float(np.sqrt(np.mean(signal[i : i + frame] ** 2))) for i in range(0, len(signal) - frame, frame)]
    if not energies:
        return PauseProfile([], 0)
    threshold = max(0.01, 0.1 * max(energies))
    voiced = [e > threshold for e in energies]
    first = voiced.index(True) if True in voiced else len(voiced)
    last = len(voiced) - voiced[::-1].index(True) if True in voiced else 0
    found, run = [], 0
    for v in voiced[first:last]:
        if v:
            if run * 10 >= min_pause_ms:
                found.append(run * 10)
            run = 0
        else:
            run += 1
    return PauseProfile(found, sum(voiced) * 10)


def speech_rate(syllables: int, profile: PauseProfile) -> float:
    """Syllables per second of phonation (articulation rate)."""
    return syllables / (profile.speech_ms / 1000) if profile.speech_ms else 0.0


def npvi(durations: list[float]) -> float:
    """Normalised pairwise variability index of successive durations (stress- vs syllable-timed rhythm)."""
    if len(durations) < 2:
        return 0.0
    pairs = list(itertools.pairwise(durations))
    return float(100 * sum(abs(a - b) / ((a + b) / 2) for a, b in pairs if a + b) / len(pairs))
