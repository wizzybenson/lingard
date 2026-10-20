"""Live-plane types: transport events, audio chunks and turn policy (SPEC §6)."""

from __future__ import annotations

import math
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from lingard_contracts.common import Frozen, Locale, Strict

SAMPLE_RATE = 16_000
"""PCM sample rate used inside the live plane (16-bit mono)."""

EOT_CAP_MS = 1_600
EOT_MARGIN_MS = 150
BASE_EOT_BY_BAND: list[tuple[int, int]] = [(4, 1_200), (6, 950), (8, 750), (12, 600)]
"""(max band inclusive, base end-of-turn silence ms), SPEC §6.2 starting values."""


class AudioChunk(Frozen):
    pcm: bytes
    sample_rate: int = SAMPLE_RATE
    timestamp_ms: int = 0

    @property
    def duration_ms(self) -> int:
        return len(self.pcm) * 1000 // (2 * self.sample_rate)


SPECULATION_SHARE = 0.4
SPECULATION_MIN_MS = 300


class TurnPolicy(Frozen):
    eot_ms: int = Field(ge=200, le=EOT_CAP_MS)
    barge_in_ms: int = 250
    backchannel_after_ms: int = 900
    semantic_eot: bool = True
    speculate: bool = True

    @property
    def speculation_ms(self) -> int:
        """Silence after which the reply is prepared speculatively (discarded if the learner resumes)."""
        return max(SPECULATION_MIN_MS, int(self.eot_ms * SPECULATION_SHARE))


def base_eot_for_band(band: int) -> int:
    for max_band, ms in BASE_EOT_BY_BAND:
        if band <= max_band:
            return ms
    return BASE_EOT_BY_BAND[-1][1]


def personalised_turn_policy(band: int, intra_pauses_ms: list[int]) -> TurnPolicy:
    """``eot_ms = max(base_by_band, p90(pauses) + 150)``, capped at 1,600 ms."""
    base = base_eot_for_band(band)
    if intra_pauses_ms:
        ordered = sorted(intra_pauses_ms)
        p90 = ordered[math.ceil(0.9 * len(ordered)) - 1]  # nearest-rank percentile
        base = max(base, p90 + EOT_MARGIN_MS)
    return TurnPolicy(eot_ms=min(base, EOT_CAP_MS))


class LiveSessionConfig(Strict):
    session_id: UUID
    user_id: UUID
    scene_id: UUID
    room: str
    locale: Locale
    policy: TurnPolicy


class LearnerSpeechStarted(Frozen):
    kind: Literal["speech_started"] = "speech_started"
    at_ms: int


class LearnerAudio(Frozen):
    """The learner's audio while they speak, in short batches, for streaming transcription. The turn's events
    still carry the whole utterance, so a consumer that ignores these loses nothing."""

    kind: Literal["learner_audio"] = "learner_audio"
    pcm: bytes
    speech_start_ms: int


class PartialTranscript(Frozen):
    kind: Literal["partial"] = "partial"
    text: str
    at_ms: int


class LearnerTurnEnded(Frozen):
    kind: Literal["turn_ended"] = "turn_ended"
    audio: bytes
    speech_start_ms: int
    speech_end_ms: int
    eot_decided_ms: int
    pauses_ms: tuple[int, ...] = ()
    interrupted_npc: bool = False


class SpeculativeTurn(Frozen):
    """The learner has paused long enough that the turn may be over: prepare a reply, but don't speak yet."""

    kind: Literal["speculate"] = "speculate"
    audio: bytes
    speech_start_ms: int
    speech_end_ms: int
    at_ms: int


class LearnerSpeechResumed(Frozen):
    """Speech resumed after a speculative pause: the prepared reply must be discarded."""

    kind: Literal["speech_resumed"] = "speech_resumed"
    speech_start_ms: int
    at_ms: int


class BargeIn(Frozen):
    kind: Literal["barge_in"] = "barge_in"
    utterance_id: str
    at_ms: int


class NetworkDegraded(Frozen):
    kind: Literal["network_degraded"] = "network_degraded"
    detail: str


class Closed(Frozen):
    kind: Literal["closed"] = "closed"
    reason: str = "normal"


LiveEvent = Annotated[
    LearnerSpeechStarted
    | LearnerAudio
    | PartialTranscript
    | LearnerTurnEnded
    | SpeculativeTurn
    | LearnerSpeechResumed
    | BargeIn
    | NetworkDegraded
    | Closed,
    Field(discriminator="kind"),
]
