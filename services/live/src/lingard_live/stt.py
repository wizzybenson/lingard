"""Speech-to-text providers on buffered learner turns (16 kHz PCM in, transcript + confidence out)."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from lingard_live.audio import pcm_to_wav

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None
    provider: str
    words: list[tuple[str, float, float]] = field(default_factory=list)
    """(word, start_s, end_s) when the provider gives timestamps (alignment and pause analysis)."""


class SttProvider(Protocol):
    name: str

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript: ...


class OpenAIStt:
    name = "openai"
    URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, api_key: str, model: str = "gpt-4o-transcribe", timeout: float = 10.0) -> None:
        self._key, self._model, self._timeout = api_key, model, timeout

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        data = {
            "model": self._model,
            "language": locale.split("-")[0],
            "response_format": "json",
            "include[]": "logprobs",
        }
        if prompt:
            data["prompt"] = prompt
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self._key}"},
                data=data,
                files={"file": ("turn.wav", pcm_to_wav(pcm), "audio/wav")},
            )
            response.raise_for_status()
            body = response.json()
        logprobs = [lp["logprob"] for lp in body.get("logprobs") or [] if "logprob" in lp]
        confidence = math.exp(sum(logprobs) / len(logprobs)) if logprobs else None
        return Transcript(text=body.get("text", "").strip(), confidence=confidence, provider=self.name)


class DeepgramStt:
    name = "deepgram"
    URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str, model: str = "nova-3", timeout: float = 10.0) -> None:
        self._key, self._model, self._timeout = api_key, model, timeout

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self.URL,
                params={"model": self._model, "language": locale.split("-")[0], "smart_format": "true"},
                headers={"Authorization": f"Token {self._key}", "Content-Type": "audio/wav"},
                content=pcm_to_wav(pcm),
            )
            response.raise_for_status()
            best = response.json()["results"]["channels"][0]["alternatives"][0]
        return Transcript(
            text=best.get("transcript", "").strip(), confidence=best.get("confidence"), provider=self.name
        )


class ElevenLabsStt:
    name = "elevenlabs"
    URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(self, api_key: str, model: str = "scribe_v2", timeout: float = 15.0) -> None:
        self._key, self._model, self._timeout = api_key, model, timeout

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self.URL,
                headers={"xi-api-key": self._key},
                data={"model_id": self._model, "language_code": locale.split("-")[0], "file_format": "pcm_s16le_16"},
                files={"file": ("turn.pcm", pcm, "application/octet-stream")},
            )
            response.raise_for_status()
            body = response.json()
        # Scribe reports language probability, not transcript confidence, so confidence stays unknown.
        return Transcript(text=body.get("text", "").strip(), confidence=None, provider=self.name)


class VoiceboxStt:
    """Self-hosted Whisper through voicebox ``POST /transcribe``."""

    name = "voicebox"

    def __init__(self, base_url: str, model: str = "whisper-turbo", timeout: float = 15.0) -> None:
        self._base, self._model, self._timeout = base_url.rstrip("/"), model, timeout

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/transcribe",
                data={"model": self._model, "language": locale.split("-")[0]},
                files={"audio": ("turn.wav", pcm_to_wav(pcm), "audio/wav")},
            )
            response.raise_for_status()
            body = response.json()
        return Transcript(text=str(body.get("text", "")).strip(), confidence=body.get("confidence"), provider=self.name)


class FallbackStt:
    def __init__(self, primary: SttProvider, fallback: SttProvider) -> None:
        self.primary, self.fallback = primary, fallback
        self.name = f"{primary.name}>{fallback.name}"

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        try:
            return await self.primary.transcribe(pcm, locale, prompt)
        except Exception:
            logger.warning("STT %s failed; falling back to %s", self.primary.name, self.fallback.name, exc_info=True)
            return await self.fallback.transcribe(pcm, locale, prompt)


class ScriptedStt:
    """Offline STT: returns queued transcripts, or asks ``responder`` (used by synthetic-learner evals)."""

    name = "scripted"

    def __init__(
        self,
        queue: list[Transcript] | None = None,
        responder: Callable[[bytes], Transcript] | None = None,
        delay_ms: int = 0,
    ) -> None:
        self.queue = list(queue or [])
        self.responder = responder
        self.delay_ms = delay_ms

    async def transcribe(self, pcm: bytes, locale: str, prompt: str | None = None) -> Transcript:
        import asyncio

        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        if self.responder is not None:
            return self.responder(pcm)
        return self.queue.pop(0)
