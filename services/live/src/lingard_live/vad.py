"""Voice activity detection and end-of-turn decisions on 16 kHz PCM (SPEC §6.2).

The detector is energy-based with an adaptive noise floor; ``Endpointer`` applies the personalised ``TurnPolicy``,
records intra-utterance pauses (which feed the next policy), and emits barge-in while the NPC is speaking.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from lingard_contracts.live import (
    SAMPLE_RATE,
    BargeIn,
    LearnerSpeechResumed,
    LearnerSpeechStarted,
    LearnerTurnEnded,
    LiveEvent,
    SpeculativeTurn,
    TurnPolicy,
)

FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


class EnergyVad:
    def __init__(self, ratio: float = 3.0, min_rms: float = 300.0, adapt: float = 0.05) -> None:
        self._ratio = ratio
        self._min_rms = min_rms
        self._adapt = adapt
        self._floor = min_rms / ratio

    def is_speech(self, frame: bytes) -> bool:
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        speech = rms > max(self._min_rms, self._floor * self._ratio)
        if not speech:
            self._floor = (1 - self._adapt) * self._floor + self._adapt * rms
        return speech


SemanticEot = Callable[[bytes], float]
"""Optional model: probability that the utterance so far is complete."""


@dataclass
class Endpointer:
    policy: TurnPolicy
    vad: EnergyVad = field(default_factory=EnergyVad)
    semantic_eot: SemanticEot | None = None
    semantic_threshold: float = 0.85
    min_speech_ms: int = 200

    _now_ms: int = field(default=0, init=False)
    _speaking: bool = field(default=False, init=False)
    _speech_ms: int = field(default=0, init=False)
    _silence_ms: int = field(default=0, init=False)
    _start_ms: int = field(default=0, init=False)
    _last_voice_ms: int = field(default=0, init=False)
    _pauses: list[int] = field(default_factory=list, init=False)
    _buffer: bytearray = field(default_factory=bytearray, init=False)
    _npc_utterance: str | None = field(default=None, init=False)
    _barge_ms: int = field(default=0, init=False)
    _interrupted: bool = field(default=False, init=False)
    _speculated: bool = field(default=False, init=False)

    def npc_started(self, utterance_id: str) -> None:
        self._npc_utterance = utterance_id
        self._barge_ms = 0

    def npc_finished(self) -> None:
        self._npc_utterance = None

    def feed(self, pcm: bytes) -> list[LiveEvent]:
        events: list[LiveEvent] = []
        for offset in range(0, len(pcm) - len(pcm) % (FRAME_SAMPLES * 2), FRAME_SAMPLES * 2):
            events.extend(self._frame(pcm[offset : offset + FRAME_SAMPLES * 2]))
        return events

    def _frame(self, frame: bytes) -> list[LiveEvent]:
        out: list[LiveEvent] = []
        self._now_ms += FRAME_MS
        voiced = self.vad.is_speech(frame)

        if self._npc_utterance is not None:
            self._barge_ms = self._barge_ms + FRAME_MS if voiced else 0
            if self._barge_ms >= self.policy.barge_in_ms:
                out.append(BargeIn(utterance_id=self._npc_utterance, at_ms=self._now_ms))
                self._npc_utterance = None
                self._interrupted = True

        if voiced:
            if not self._speaking:
                self._speaking = True
                self._start_ms = self._now_ms - FRAME_MS
                self._speech_ms = 0
                self._pauses = []
                self._buffer = bytearray()
                out.append(LearnerSpeechStarted(at_ms=self._start_ms))
            elif self._silence_ms >= 120:
                self._pauses.append(self._silence_ms)
            if self._speculated:
                out.append(LearnerSpeechResumed(speech_start_ms=self._start_ms, at_ms=self._now_ms))
                self._speculated = False
            self._silence_ms = 0
            self._speech_ms += FRAME_MS
            self._last_voice_ms = self._now_ms
        elif self._speaking:
            self._silence_ms += FRAME_MS

        if self._speaking:
            self._buffer.extend(frame)
            if (
                self.policy.speculate
                and not self._speculated
                and self._speech_ms >= self.min_speech_ms
                and self._silence_ms >= self.policy.speculation_ms
                and self._silence_ms < self.policy.eot_ms
            ):
                self._speculated = True
                out.append(
                    SpeculativeTurn(
                        audio=bytes(self._buffer),
                        speech_start_ms=self._start_ms,
                        speech_end_ms=self._last_voice_ms,
                        at_ms=self._now_ms,
                    )
                )
            if self._silence_ms and self._speech_ms >= self.min_speech_ms and self._turn_complete():
                out.append(
                    LearnerTurnEnded(
                        audio=bytes(self._buffer),
                        speech_start_ms=self._start_ms,
                        speech_end_ms=self._last_voice_ms,
                        eot_decided_ms=self._now_ms,
                        pauses_ms=tuple(self._pauses),
                        interrupted_npc=self._interrupted,
                    )
                )
                self._speaking = False
                self._silence_ms = 0
                self._interrupted = False
                self._speculated = False
            elif self._silence_ms >= self.policy.eot_ms and self._speech_ms < self.min_speech_ms:
                self._speaking = False  # a cough or click: discard
                self._silence_ms = 0
        return out

    def _turn_complete(self) -> bool:
        if self._silence_ms >= self.policy.eot_ms:
            return True
        early = self.policy.semantic_eot and self.semantic_eot is not None and self._silence_ms >= 300
        return bool(
            early
            and self.semantic_eot is not None
            and self.semantic_eot(bytes(self._buffer)) >= self.semantic_threshold
        )
