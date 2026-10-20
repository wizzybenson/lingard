"""``VoiceTransport`` (SPEC §6.1) and an in-memory loopback implementation for tests, evals and CI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from lingard_contracts.live import AudioChunk, Closed, LiveEvent, LiveSessionConfig, TurnPolicy
from lingard_live.vad import SemanticEot


class LiveSession(Protocol):
    def events(self) -> AsyncIterator[LiveEvent]: ...

    async def speak(self, stream: AsyncIterator[AudioChunk], utterance_id: str) -> None: ...

    async def cancel_speech(self, utterance_id: str) -> None: ...

    async def set_turn_policy(self, policy: TurnPolicy) -> None: ...

    def set_semantic_eot(self, model: SemanticEot | None) -> None:
        """Lets the endpointer end a turn early when ``model`` says the utterance so far is complete."""
        ...

    async def caption(self, speaker: str, text: str) -> None:
        """Send a caption line to the learner's client (NPC sentences as they play, the learner's transcript)."""
        ...

    async def close(self) -> None: ...


class VoiceTransport(Protocol):
    async def open(self, cfg: LiveSessionConfig) -> LiveSession: ...


@dataclass
class SpokenUtterance:
    utterance_id: str
    chunks: list[AudioChunk] = field(default_factory=list)
    cancelled: bool = False


class LoopbackSession:
    """Test double: events are pushed by the test; spoken audio is recorded instead of played."""

    def __init__(self, cfg: LiveSessionConfig) -> None:
        self.cfg = cfg
        self.policy = cfg.policy
        self.spoken: list[SpokenUtterance] = []
        self._queue: asyncio.Queue[LiveEvent] = asyncio.Queue()
        self._cancelled: set[str] = set()
        self.captions: list[tuple[str, str]] = []
        self.semantic_eot: SemanticEot | None = None
        """Recorded for tests; a loopback session has no endpointer of its own."""
        self.closed = False

    def push(self, event: LiveEvent) -> None:
        self._queue.put_nowait(event)

    async def events(self) -> AsyncIterator[LiveEvent]:
        while True:
            event = await self._queue.get()
            yield event
            if isinstance(event, Closed):
                return

    async def speak(self, stream: AsyncIterator[AudioChunk], utterance_id: str) -> None:
        utterance = SpokenUtterance(utterance_id)
        self.spoken.append(utterance)
        async for chunk in stream:
            if utterance_id in self._cancelled:
                utterance.cancelled = True
                break
            utterance.chunks.append(chunk)
            await asyncio.sleep(0)

    async def cancel_speech(self, utterance_id: str) -> None:
        self._cancelled.add(utterance_id)
        for utterance in self.spoken:
            if utterance.utterance_id == utterance_id:
                utterance.cancelled = True

    async def set_turn_policy(self, policy: TurnPolicy) -> None:
        self.policy = policy

    def set_semantic_eot(self, model: SemanticEot | None) -> None:
        self.semantic_eot = model

    async def caption(self, speaker: str, text: str) -> None:
        self.captions.append((speaker, text))

    async def close(self) -> None:
        self.closed = True
        self._queue.put_nowait(Closed(reason="closed_by_server"))


class LoopbackTransport:
    def __init__(self) -> None:
        self.sessions: list[LoopbackSession] = []

    async def open(self, cfg: LiveSessionConfig) -> LoopbackSession:
        session = LoopbackSession(cfg)
        self.sessions.append(session)
        return session
