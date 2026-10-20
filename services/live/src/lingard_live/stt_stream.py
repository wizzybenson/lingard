"""Streaming speech-to-text: the learner's audio is transcribed while they speak, so when the turn ends only a
commit is left (measured 2026-10-20: ~270 ms from commit to final text with ElevenLabs Scribe v2 Realtime, against
~800–1,000 ms for batch transcription of the whole turn).

One stream per utterance. ``finish`` commits what has been fed and returns everything said since the utterance began;
it can be called again after more audio (a speculative turn the learner then continued). Any failure raises, and the
loop falls back to batch transcription of the same audio, so streaming can only make a turn faster, never lose it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from typing import Any, Protocol

import websockets

from lingard_contracts.live import SAMPLE_RATE
from lingard_live.stt import Transcript

logger = logging.getLogger(__name__)

MIN_COMMIT_BYTES = int(SAMPLE_RATE * 2 * 0.3)
"""Scribe refuses a commit of under 0.3 s of new audio (``commit_throttled``)."""


class SttStream(Protocol):
    async def feed(self, pcm: bytes) -> None: ...

    def partial(self) -> str:
        """Everything heard so far, including the provider's not-yet-committed guess (for semantic end of turn)."""
        ...

    async def finish(self, timeout_s: float) -> Transcript: ...

    async def close(self) -> None: ...


class StreamingStt(Protocol):
    name: str

    def open(self, locale: str) -> SttStream:
        """Start connecting now; audio fed before the connection is ready is buffered."""
        ...


class ElevenLabsRealtimeStt:
    name = "elevenlabs-realtime"
    URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def __init__(self, api_key: str, model: str = "scribe_v2_realtime") -> None:
        self._key, self._model = api_key, model

    def open(self, locale: str) -> ElevenLabsStream:
        query = f"model_id={self._model}&audio_format=pcm_{SAMPLE_RATE}&language_code={locale.split('-')[0]}"
        return ElevenLabsStream(f"{self.URL}?{query}", self._key, self.name)


class ElevenLabsStream:
    def __init__(self, url: str, key: str, provider: str) -> None:
        self._provider = provider
        self._outbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._committed: list[str] = []
        """Every committed segment in arrival order, kept by the reader: a ``finish`` cancelled while waiting (a
        speculation the learner talked over) must not leave its text for the next ``finish`` to mistake as its own."""
        self._partial = ""
        self._requested = 0
        self._answered = 0
        self._arrived = asyncio.Event()
        self._uncommitted = 0
        self._failed: BaseException | None = None
        self._task = asyncio.create_task(self._run(url, key))

    async def _run(self, url: str, key: str) -> None:
        try:
            async with websockets.connect(url, additional_headers={"xi-api-key": key}, open_timeout=5) as ws:
                started = json.loads(await ws.recv())
                if started.get("message_type") != "session_started":
                    raise RuntimeError(f"realtime STT did not start: {started}")
                reader = asyncio.create_task(self._read(ws))
                try:
                    while (message := await self._outbox.get()) is not None:
                        await ws.send(json.dumps(message))
                finally:
                    reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
        except Exception as exc:  # recorded; finish() raises it and the loop falls back to batch
            self._failed = exc
            self._arrived.set()

    async def _read(self, ws: Any) -> None:
        async for raw in ws:
            message = json.loads(raw)
            kind = message.get("message_type", "")
            if kind == "partial_transcript":
                self._partial = str(message.get("text", "")).strip()
            elif kind == "committed_transcript" or kind == "commit_throttled":  # throttled: the text so far stands
                if text := str(message.get("text", "")).strip():
                    self._committed.append(text)
                self._partial = ""
                self._answered += 1
                self._arrived.set()
            elif kind not in ("session_started", "committed_transcript_with_timestamps"):
                logger.warning("realtime STT error %s", message)
                self._failed = RuntimeError(str(message))
                self._arrived.set()

    def _chunk(self, pcm: bytes, commit: bool) -> dict[str, Any]:
        return {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(pcm).decode(),
            "commit": commit,
            "sample_rate": SAMPLE_RATE,
        }

    async def feed(self, pcm: bytes) -> None:
        self._uncommitted += len(pcm)
        await self._outbox.put(self._chunk(pcm, False))

    def partial(self) -> str:
        return " ".join([*self._committed, self._partial]).strip()

    async def finish(self, timeout_s: float) -> Transcript:
        if self._failed is not None:
            raise RuntimeError("realtime STT failed") from self._failed
        if self._uncommitted >= MIN_COMMIT_BYTES:
            self._uncommitted = 0
            self._requested += 1
            await self._outbox.put(self._chunk(b"", True))
        async with asyncio.timeout(timeout_s):
            while self._answered < self._requested and self._failed is None:
                self._arrived.clear()
                await self._arrived.wait()
        if self._failed is not None:
            raise RuntimeError("realtime STT failed") from self._failed
        return Transcript(text=" ".join(self._committed).strip(), confidence=None, provider=self._provider)

    async def close(self) -> None:
        await self._outbox.put(None)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(self._task), 2)
        self._task.cancel()


class ScriptedStreamingStt:
    """Offline: each commit returns the next scripted segment after ``commit_ms``; ``fail`` makes every stream fail."""

    name = "scripted-stream"

    def __init__(self, segments: list[str], commit_ms: int = 0, fail: bool = False, partial: str = "") -> None:
        self.segments = list(segments)
        self.partial = partial
        """What every stream reports as heard so far, before any commit."""
        self.commit_ms = commit_ms
        self.fail = fail
        self.fed = 0
        self.opened = 0

    def open(self, locale: str) -> ScriptedStream:
        self.opened += 1
        return ScriptedStream(self)


class ScriptedStream:
    """Like the provider, a commit is answered in the background: a ``finish`` cancelled while waiting loses nothing."""

    def __init__(self, owner: ScriptedStreamingStt) -> None:
        self._owner = owner
        self._committed: list[str] = []
        self._uncommitted = 0
        self._answers: list[asyncio.Task[None]] = []

    async def feed(self, pcm: bytes) -> None:
        self._owner.fed += len(pcm)
        self._uncommitted += len(pcm)

    def partial(self) -> str:
        return " ".join([*self._committed, self._owner.partial]).strip()

    async def finish(self, timeout_s: float) -> Transcript:
        if self._owner.fail:
            raise RuntimeError("scripted failure")
        if self._uncommitted >= MIN_COMMIT_BYTES and self._owner.segments:
            self._uncommitted = 0
            self._answers.append(asyncio.create_task(self._answer(self._owner.segments.pop(0))))
        await asyncio.wait_for(asyncio.gather(*map(asyncio.shield, self._answers)), timeout_s)
        return Transcript(text=" ".join(self._committed), confidence=None, provider=self._owner.name)

    async def _answer(self, segment: str) -> None:
        await asyncio.sleep(self._owner.commit_ms / 1000)
        self._committed.append(segment)

    async def close(self) -> None:
        for task in self._answers:
            task.cancel()
