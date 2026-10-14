"""Accent Studio loop (SPEC §13.4): hear golden self → shadow → heatmap + pitch overlay → ≤ 3 retries → FSRS."""

from __future__ import annotations

from dataclasses import dataclass, field

from lingard_pronunciation.gop import score_phonemes
from lingard_pronunciation.prosody import contour_similarity, semitone_contour, to_float, yin_f0
from lingard_pronunciation.recognizer import PhonemeRecognizer
from lingard_pronunciation.scoring import PronReport, PronTarget, report

MAX_ATTEMPTS = 3
PASS_SCORE = 70.0


@dataclass
class ShadowAttempt:
    report: PronReport
    learner_pitch: list[float]
    reference_pitch: list[float]


@dataclass
class StudioItem:
    line: str
    expected_phonemes: list[str]
    targets: list[PronTarget]
    reference_pcm: bytes
    attempts: list[ShadowAttempt] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return len(self.attempts) >= MAX_ATTEMPTS or self.passed

    @property
    def passed(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].report.intelligibility >= PASS_SCORE

    def review_grade(self) -> tuple[bool, bool]:
        """(correct, hesitant) for the FSRS card: pass first time = Good, pass on retry = Hard, never = Again."""
        return self.passed, self.passed and len(self.attempts) > 1


def shadow(item: StudioItem, learner_pcm: bytes, recognizer: PhonemeRecognizer) -> ShadowAttempt:
    if item.done:
        raise ValueError("no attempts left for this line")
    posteriors = recognizer.log_posteriors(learner_pcm)
    scores = score_phonemes(posteriors, item.expected_phonemes, recognizer.inventory)
    learner_f0 = yin_f0(to_float(learner_pcm))
    reference_f0 = yin_f0(to_float(item.reference_pcm))
    attempt = ShadowAttempt(
        report=report(scores, item.targets, intonation=contour_similarity(learner_f0, reference_f0)),
        learner_pitch=[round(x, 2) for x in semitone_contour(learner_f0)],
        reference_pitch=[round(x, 2) for x in semitone_contour(reference_f0)],
    )
    item.attempts.append(attempt)
    return attempt
