"""CTC forced alignment and goodness of pronunciation (GOP) from phoneme posteriors.

The recogniser supplies log-posteriors [frames × phonemes] (blank at index 0); alignment is Viterbi over the CTC
topology of the expected phoneme sequence. GOP per phoneme = mean over its frames of
log p(expected) − log max p(any non-blank), so 0 is native-like and strongly negative means another phoneme won.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

BLANK = 0


@dataclass(frozen=True)
class PhonemeScore:
    phoneme: str
    start_frame: int
    end_frame: int
    gop: float
    score: float
    """0–100, from GOP through a logistic calibrated so GOP = −1 ≈ 50."""
    likely_substitute: str | None


def align(log_probs: NDArray[np.float64], targets: list[int]) -> list[tuple[int, int]]:
    """Frame span (start, end inclusive) per target token via CTC Viterbi. Raises if the audio is too short."""
    frames = log_probs.shape[0]
    states = [BLANK]
    for t in targets:
        states += [t, BLANK]
    n = len(states)
    if frames < len(targets):
        raise ValueError("audio too short for the expected phonemes")
    score = np.full((frames, n), -np.inf)
    back = np.zeros((frames, n), dtype=np.int64)
    score[0, 0] = log_probs[0, states[0]]
    if n > 1:
        score[0, 1] = log_probs[0, states[1]]
    for f in range(1, frames):
        for s in range(n):
            options = [(score[f - 1, s], s)]
            if s >= 1:
                options.append((score[f - 1, s - 1], s - 1))
            if s >= 2 and states[s] != BLANK and states[s] != states[s - 2]:
                options.append((score[f - 1, s - 2], s - 2))
            best, prev = max(options)
            score[f, s] = best + log_probs[f, states[s]]
            back[f, s] = prev
    s = n - 1 if score[-1, n - 1] >= score[-1, n - 2] else n - 2
    path = [s]
    for f in range(frames - 1, 0, -1):
        s = int(back[f, s])
        path.append(s)
    path.reverse()
    spans: list[tuple[int, int]] = []
    for index in range(len(targets)):
        frames_for = [f for f, st in enumerate(path) if st == 2 * index + 1]
        if not frames_for:
            raise ValueError("alignment failed")
        spans.append((frames_for[0], frames_for[-1]))
    return spans


def score_phonemes(
    log_probs: NDArray[np.float64],
    expected: list[str],
    inventory: list[str],
    variants: dict[str, list[str]] | None = None,
) -> list[PhonemeScore]:
    """``inventory[0]`` must be the blank symbol; ``expected`` uses inventory symbols. ``variants`` are realisations
    native speakers use for a phoneme (French /œ̃/ is /ɛ̃/ for most): the best of them counts as the phoneme."""
    index = {p: i for i, p in enumerate(inventory)}
    targets = [index[p] for p in expected]
    spans = align(log_probs, targets)
    results = []
    for phoneme, target, (start, end) in zip(expected, targets, spans, strict=True):
        window = log_probs[start : end + 1]
        non_blank = window[:, 1:]
        best = non_blank.max(axis=1)
        accepted = [target] + [index[v] for v in (variants or {}).get(phoneme, []) if v in index]
        gop = float(np.mean(window[:, accepted].max(axis=1) - best))
        winners = non_blank.argmax(axis=1) + 1
        top = int(np.bincount(winners).argmax())
        substitute = inventory[top] if top not in accepted else None
        results.append(PhonemeScore(phoneme, start, end, gop, 100 / (1 + math.exp(-(gop + 1) * 3)), substitute))
    return results
