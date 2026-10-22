"""The music of an accent, syllable by syllable (decision 0028): word stress, sentence emphasis, rhythm and intonation.

Both the learner's take and the native reference are aligned to the same expected sounds, so each syllable's vowel
(its nucleus) can be measured in both: how long it lasts, how loud it is, how high the voice is. A syllable stands out
(is prominent) when it is longer, louder and higher than the speaker's own average; comparing the two speakers
syllable by syllable then answers the questions an accent coach asks:

- word stress: in each word of two or more syllables, is the syllable that stands out the same one?
- emphasis: in the sentence, does the word that carries the weight match?
- rhythm: do the syllables keep the same relative lengths (English squeezes unstressed ones; French keeps them even
  and lengthens the last of a group)?
- intonation: does the pitch move the same way, above all at the end (a question rises, a statement falls)?

Everything is relative to each speaker's own voice, so a deep voice and a high one compare fairly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from lingard_pronunciation.gop import PhonemeScore
from lingard_pronunciation.prosody import HOP, SAMPLE_RATE, to_float, yin_f0

FRAME_S = 0.02
"""wav2vec2 frames are 20 ms apart."""
PAD_FRAMES = 15
"""The recogniser pads 0.3 s of silence before the audio (``recognizer.PAD_S``)."""
FINAL_MOVE = 1.5
"""Semitones of final pitch movement that count as a rise or a fall."""


@dataclass
class Nucleus:
    word: int
    syllable: str
    duration: float
    energy: float
    pitch: float | None
    prominence: float = 0.0


def _syllables(phonemes: list[str], vowels: set[str]) -> list[str]:
    """A word's sounds grouped around its vowels: consonants before a vowel open its syllable, the last ones close the
    last syllable. Only for display: "fo·to·ɡʁaf"."""
    groups: list[str] = []
    pending = ""
    for p in phonemes:
        pending += p
        if p in vowels:
            groups.append(pending)
            pending = ""
    if groups and pending:
        groups[-1] += pending
    return groups or ["".join(phonemes)]


def _measure(
    pcm: bytes, spans: list[PhonemeScore], words: list[tuple[str, list[str]]], vowels: set[str]
) -> list[Nucleus]:
    signal = to_float(pcm)
    f0 = yin_f0(signal)
    voiced = f0[f0 > 0]
    register = float(np.median(voiced)) if voiced.size else 0.0
    nuclei: list[Nucleus] = []
    at = 0
    for w, (_text, phonemes) in enumerate(words):
        labels = iter(_syllables(phonemes, vowels))
        for p in phonemes:
            span = spans[at]
            at += 1
            if p not in vowels:
                continue
            start = max(span.start_frame - PAD_FRAMES, 0) * FRAME_S
            end = max(span.end_frame + 1 - PAD_FRAMES, 1) * FRAME_S
            chunk = signal[int(start * SAMPLE_RATE) : max(int(end * SAMPLE_RATE), int(start * SAMPLE_RATE) + 1)]
            energy = 20 * math.log10(float(np.sqrt(np.mean(chunk**2))) + 1e-6)
            track = f0[int(start * SAMPLE_RATE / HOP) : int(end * SAMPLE_RATE / HOP) + 1]
            track = track[track > 0]
            pitch = float(12 * np.log2(np.median(track) / register)) if track.size and register else None
            nuclei.append(Nucleus(w, next(labels, p), max(end - start, FRAME_S), energy, pitch))
    _prominence(nuclei)
    return nuclei


def _z(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=np.float64)
    spread = float(arr.std()) or 1.0
    return [float(x) for x in (arr - arr.mean()) / spread]


def _prominence(nuclei: list[Nucleus]) -> None:
    """Longer, louder and higher than this speaker's own average, in equal parts."""
    if not nuclei:
        return
    durations = _z([math.log(n.duration) for n in nuclei])
    energies = _z([n.energy for n in nuclei])
    pitched = [n.pitch for n in nuclei if n.pitch is not None]
    mean, spread = (float(np.mean(pitched)), float(np.std(pitched)) or 1.0) if pitched else (0.0, 1.0)
    for n, d, e in zip(nuclei, durations, energies, strict=True):
        p = (n.pitch - mean) / spread if n.pitch is not None else 0.0
        n.prominence = d + e + p


def _word_stress(you: list[Nucleus], ref: list[Nucleus], words: list[tuple[str, list[str]]]) -> dict[str, Any] | None:
    checked = []
    for w, (text, _) in enumerate(words):
        mine = [n for n in you if n.word == w]
        theirs = [n for n in ref if n.word == w]
        if len(theirs) < 2 or len(mine) != len(theirs):
            continue
        expected = int(np.argmax([n.prominence for n in theirs]))
        yours = int(np.argmax([n.prominence for n in mine]))
        checked.append({"word": text, "syllables": [n.syllable for n in theirs], "expected": expected, "yours": yours})
    if not checked:
        return None
    right = sum(c["expected"] == c["yours"] for c in checked)
    return {"score": round(100 * right / len(checked), 1), "words": checked}


def _word_weights(nuclei: list[Nucleus], count: int) -> list[float]:
    return [max((n.prominence for n in nuclei if n.word == w), default=-9.0) for w in range(count)]


def _rank_correlation(a: list[float], b: list[float]) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def _emphasis(you: list[Nucleus], ref: list[Nucleus], words: list[tuple[str, list[str]]]) -> dict[str, Any] | None:
    if len(words) < 3:
        return None
    theirs, mine = _word_weights(ref, len(words)), _word_weights(you, len(words))
    expected, yours = int(np.argmax(theirs)), int(np.argmax(mine))
    agreement = (_rank_correlation(theirs, mine) + 1) / 2
    score = 100 * (0.5 * (expected == yours) + 0.5 * agreement)
    return {
        "score": round(score, 1),
        "expected": words[expected][0],
        "yours": words[yours][0],
        "model": [round(x, 2) for x in theirs],
        "you": [round(x, 2) for x in mine],
    }


def _rhythm(you: list[Nucleus], ref: list[Nucleus]) -> dict[str, Any] | None:
    if len(ref) < 3 or len(you) != len(ref):
        return None
    mine = np.log([n.duration for n in you])
    theirs = np.log([n.duration for n in ref])
    gap = float(np.mean(np.abs((mine - mine.mean()) - (theirs - theirs.mean()))))
    pace = float(np.sum(np.exp(mine)) / np.sum(np.exp(theirs)))
    longest = int(np.argmax(theirs - theirs.mean() - (mine - mine.mean())))
    return {
        "score": round(100 * max(0.0, 1 - gap / 0.6), 1),
        "pace": round(pace, 2),
        "stretch": ref[longest].syllable,  # the syllable the model holds longest compared with the learner
        "model": [round(float(x), 3) for x in np.exp(theirs)],
        "you": [round(float(x), 3) for x in np.exp(mine)],
    }


def _movement(nuclei: list[Nucleus]) -> str | None:
    pitched = [n.pitch for n in nuclei if n.pitch is not None]
    if len(pitched) < 2:
        return None
    before = float(np.mean(pitched[-3:-1])) if len(pitched) >= 3 else pitched[-2]
    move = pitched[-1] - before
    return "rise" if move > FINAL_MOVE else "fall" if move < -FINAL_MOVE else "level"


def _intonation(you: list[Nucleus], ref: list[Nucleus]) -> dict[str, Any] | None:
    if len(ref) < 3 or len(you) != len(ref):
        return None
    pairs = [(a.pitch, b.pitch) for a, b in zip(you, ref, strict=True) if a.pitch is not None and b.pitch is not None]
    if len(pairs) < 3:
        return None
    mine = np.array([a for a, _ in pairs])
    theirs = np.array([b for _, b in pairs])
    gap = float(np.mean(np.abs((mine - mine.mean()) - (theirs - theirs.mean()))))
    expected, yours = _movement(ref), _movement(you)
    score = 100 * max(0.0, 1 - gap / 4)
    if expected and yours and expected != yours:
        score *= 0.6  # the end of a sentence carries its meaning: a question that falls is heard as a statement
    return {
        "score": round(score, 1),
        "final": {"expected": expected, "yours": yours},
        "model": [None if n.pitch is None else round(n.pitch, 2) for n in ref],
        "you": [None if n.pitch is None else round(n.pitch, 2) for n in you],
    }


def analyse(
    learner_pcm: bytes,
    learner: list[PhonemeScore],
    reference_pcm: bytes,
    reference: list[PhonemeScore],
    words: list[tuple[str, list[str]]],
    vowels: set[str],
) -> dict[str, Any]:
    """Stress, emphasis, rhythm and intonation of a take against the native reference; a part that doesn't apply (no
    word of two syllables, a single word) is ``None``."""
    you = _measure(learner_pcm, learner, words, vowels)
    ref = _measure(reference_pcm, reference, words, vowels)
    return {
        "syllables": [
            {
                "word": r.word,
                "text": r.syllable,
                "model": {"length": round(r.duration, 3), "weight": round(r.prominence, 2), "pitch": r.pitch},
                "you": {"length": round(y.duration, 3), "weight": round(y.prominence, 2), "pitch": y.pitch},
            }
            for r, y in zip(ref, you, strict=True)
        ],
        "stress": _word_stress(you, ref, words),
        "emphasis": _emphasis(you, ref, words),
        "rhythm": _rhythm(you, ref),
        "intonation": _intonation(you, ref),
    }
