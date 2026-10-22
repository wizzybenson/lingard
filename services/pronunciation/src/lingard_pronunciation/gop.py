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
MISSING = "∅"
"""A partner meaning "the sound was left out" ("at" for "hat"): judged against silence, the CTC blank."""


@dataclass(frozen=True)
class PhonemeScore:
    phoneme: str
    start_frame: int
    end_frame: int
    gop: float
    score: float
    """0–100, from GOP through a logistic calibrated so GOP = −1 ≈ 50."""
    likely_substitute: str | None
    contrast: float | None = None
    checked: bool = True
    """False when this recogniser can't reliably tell the sound from its trained partner (compare by ear instead)."""
    """Log-likelihood ratio of this sound against its minimal-pair partner over its own frames (decision 0028):
    positive leans toward the target, negative toward the partner. ``None`` when no partner was asked for."""


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


def calibrated_score(gop: float, p10: float, p50: float) -> float:
    """0–100 against native speech (decision 0028): a sound as good as a typical native one (the median) scores 98,
    one at the edge of native range (10th percentile) about 75, and clearly worse falls fast."""
    z = (gop - p10) / max(p50 - p10, 0.5)
    score = 100 / (1 + math.exp(-(3 * z + 1.1)))
    # Most native takes of some sounds sit exactly at the median (GOP 0, nothing heard better): that is native.
    return max(score, 98.0) if gop >= p50 else score


def tokens_of(phoneme: str, index: dict[str, int]) -> list[int]:
    """A sound as the recogniser writes it: one symbol, or (for models that write a nasal vowel as vowel + tilde) a
    few. Raises ``KeyError`` when the recogniser can't write it."""
    if phoneme == MISSING:
        return [BLANK]
    if phoneme in index:
        return [index[phoneme]]
    return [index[ch] for ch in phoneme]


def score_phonemes(
    log_probs: NDArray[np.float64],
    expected: list[str],
    inventory: list[str],
    variants: dict[str, list[str]] | None = None,
    competitors: set[str] | None = None,
    calibration: dict[str, tuple[float, float]] | None = None,
    partners: dict[str, list[str]] | None = None,
) -> list[PhonemeScore]:
    """``inventory[0]`` must be the blank symbol. ``variants`` are realisations native speakers use for a sound (French
    /œ̃/ is /ɛ̃/ for most): the best of them counts as the sound. ``competitors``: the sounds a sound is judged against
    (its language's own sounds and the learner mistakes it trains), so a multilingual recogniser's tone-marked or
    foreign symbols can't count against a native sound; ``None`` judges against every symbol. ``calibration``: native
    (10th, 50th) percentile GOP per sound, which turns GOP into a score against native speech; without it, a fixed
    curve (GOP −1 ≈ 50). ``partners``: per sound, the minimal-pair partners to measure it against (``contrast``).

    A sound written with several symbols is scored by its weakest symbol: a nasal vowel whose tilde is missing was
    said as the plain vowel."""
    index = {p: i for i, p in enumerate(inventory)}
    owned = [tokens_of(p, index) for p in expected]
    flat = [t for tokens in owned for t in tokens]
    spans = align(log_probs, flat)
    rival_set = set(flat)
    for c in competitors if competitors is not None else []:
        try:
            rival_set |= set(tokens_of(c, index))
        except KeyError:
            continue
    rivals = np.arange(1, len(inventory)) if competitors is None else np.array(sorted(rival_set))
    results = []
    at = 0
    for phoneme, tokens in zip(expected, owned, strict=True):
        own = spans[at : at + len(tokens)]
        at += len(tokens)
        alternatives = []
        for v in (variants or {}).get(phoneme, []):
            try:
                alt = tokens_of(v, index)
            except KeyError:
                continue
            if len(alt) == len(tokens):
                alternatives.append(alt)
        per_token = []
        for j, (token, (start, end)) in enumerate(zip(tokens, own, strict=True)):
            window = log_probs[start : end + 1]
            accepted = sorted({token, *(alt[j] for alt in alternatives)})
            columns = np.union1d(rivals, accepted)
            gop = float(np.mean(window[:, accepted].max(axis=1) - window[:, columns].max(axis=1)))
            winners = columns[window[:, columns].argmax(axis=1)]
            top = int(np.bincount(winners).argmax())
            per_token.append((gop, j, top, accepted))
        gop, weakest, top, accepted = min(per_token)
        if top in accepted:
            substitute = None
        elif weakest > 0:  # a mark (the nasal tilde) is missing: the plain sound was said
            substitute = phoneme.replace(inventory[tokens[weakest]], "")
        else:  # the base sound was another: keep the marks that were said right
            substitute = inventory[top] + "".join(inventory[t] for t in tokens[1:])
        cal = (calibration or {}).get(phoneme)
        score = calibrated_score(gop, *cal) if cal else 100 / (1 + math.exp(-(gop + 1) * 3))
        contrast = None
        for partner in (partners or {}).get(phoneme, []):
            value = contrast_llr(log_probs, own, tokens, partner, index)
            if value is not None:
                contrast = value if contrast is None else min(contrast, value)
        results.append(PhonemeScore(phoneme, own[0][0], own[-1][1], gop, score, substitute, contrast))
    return results


def contrast_llr(
    log_probs: NDArray[np.float64], spans: list[tuple[int, int]], tokens: list[int], partner: str, index: dict[str, int]
) -> float | None:
    """Mean log p(target) − log p(partner) over the frames where the two sounds are written differently: the targeted
    two-way test minimal-pair training needs (is this "u" closer to "u" or to "ou"?), where GOP against every sound
    lets a third sound blur the answer."""
    try:
        other = tokens_of(partner, index)
    except KeyError:
        return None
    if len(other) != len(tokens):
        other = other[:1] + tokens[1:] if len(other) < len(tokens) else other[: len(tokens)]
    rows = [
        log_probs[start : end + 1, t] - log_probs[start : end + 1, o]
        for t, o, (start, end) in zip(tokens, other, spans, strict=True)
        if t != o
    ]
    return float(np.mean(np.concatenate(rows))) if rows else None
