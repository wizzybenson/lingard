"""Text-to-speech providers streaming 16 kHz PCM.

Adapted from simupatient@69e1bd5:backend/app/services/speech_service.py: the provider interface, the ElevenLabs and
OpenAI adapters, and the fallback rule (fail over only before the first audio byte). New: PCM output for WebRTC,
the self-hosted voicebox adapter (primary, SPEC §2), and a keyed synthesis cache.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from lingard_contracts.live import SAMPLE_RATE, AudioChunk
from lingard_live.audio import chunked, resample, silence, tone, wav_to_pcm, whole_samples
from lingard_live.voices import OPENAI_VOICES, gender_of, pick

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceSpec:
    """Which voice says the line. ``voice_id`` is the provider's id (voicebox profile, ElevenLabs voice…)."""

    voice_id: str
    language: str
    rate: str = "normal"
    style: str = ""


class TtsProvider(Protocol):
    name: str

    def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]: ...


class ElevenLabsTts:
    name = "elevenlabs"
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    VOICES_URL = "https://api.elevenlabs.io/v1/voices"
    PRIVATE_VOICE_CATEGORIES = frozenset({"cloned", "generated"})
    """Never an NPC's voice: learners' clones live in the same account (biometric, owner only, SPEC §23), and
    designed voices were made for something else. NPCs speak with stock and library voices."""

    def __init__(
        self,
        api_key: str,
        model: str = "eleven_flash_v2_5",
        voices: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._key = api_key
        self._model = model
        self._voices = voices or {}
        self._timeout = timeout
        self._pools: dict[str, list[str]] | None = None

    async def voice_for(self, logical_id: str) -> str:
        """Override, else a stable pick among the account's voices of the same gender (fetched once)."""
        if logical_id in self._voices:
            return self._voices[logical_id]
        if self._pools is None:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self.VOICES_URL, headers={"xi-api-key": self._key})
                response.raise_for_status()
            pools: dict[str, list[str]] = {"f": [], "m": [], "all": []}
            for item in sorted(response.json().get("voices", []), key=lambda v: v["voice_id"]):
                if item.get("category") in self.PRIVATE_VOICE_CATEGORIES:
                    continue
                gender = str((item.get("labels") or {}).get("gender", "")).lower()
                pools["all"].append(item["voice_id"])
                if gender in ("female", "male"):
                    pools[gender[0]].append(item["voice_id"])
            if not pools["all"]:
                raise RuntimeError("the ElevenLabs account has no voices; add some or pin them in config/voices.yaml")
            self._pools = pools
        return pick(self._pools[gender_of(logical_id)] or self._pools["all"], logical_id)

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        body = {
            "text": text,
            "model_id": self._model,
            "language_code": voice.language,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True},
        }
        voice_id = await self.voice_for(voice.voice_id)
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST",
                self.URL.format(voice_id=voice_id),
                params={"output_format": f"pcm_{SAMPLE_RATE}"},
                headers={"xi-api-key": self._key},
                json=body,
            ) as response,
        ):
            response.raise_for_status()
            offset = 0
            async for data in whole_samples(response.aiter_bytes()):
                yield AudioChunk(pcm=data, timestamp_ms=offset)
                offset += len(data) * 1000 // (2 * SAMPLE_RATE)


class OpenAITts:
    name = "openai"
    URL = "https://api.openai.com/v1/audio/speech"
    SOURCE_RATE = 24_000

    def __init__(
        self, api_key: str, model: str = "gpt-4o-mini-tts", voices: dict[str, str] | None = None, timeout: float = 10.0
    ) -> None:
        self._key = api_key
        self._model = model
        self._voices = voices or {}
        self._timeout = timeout

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        body = {
            "model": self._model,
            "voice": self._voices.get(voice.voice_id) or pick(OPENAI_VOICES[gender_of(voice.voice_id)], voice.voice_id),
            "input": text,
            "instructions": voice.style,
            "response_format": "pcm",
        }
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream("POST", self.URL, headers={"Authorization": f"Bearer {self._key}"}, json=body) as response,
        ):
            response.raise_for_status()
            async for data in whole_samples(response.aiter_bytes()):
                yield AudioChunk(pcm=resample(data, self.SOURCE_RATE))


class VoiceboxTts:
    """Self-hosted jamiepine/voicebox (MIT). ``POST /generate`` with a voice profile returns WAV."""

    name = "voicebox"

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/generate", json={"text": text, "profile_id": voice.voice_id, "language": voice.language}
            )
            response.raise_for_status()
            pcm = wav_to_pcm(response.content)
        for piece in chunked(pcm):
            yield AudioChunk(pcm=piece)


class FallbackTts:
    """Primary first; fall back only if it fails before any audio was produced (never switch voice mid-sentence)."""

    def __init__(self, primary: TtsProvider, fallback: TtsProvider) -> None:
        self.primary, self.fallback = primary, fallback
        self.name = f"{primary.name}>{fallback.name}"

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        started = False
        try:
            async for chunk in self.primary.stream(text, voice):
                started = True
                yield chunk
        except Exception:
            if started:
                raise
            logger.warning("TTS %s failed; falling back to %s", self.primary.name, self.fallback.name, exc_info=True)
            async for chunk in self.fallback.stream(text, voice):
                yield chunk


class ScriptedTts:
    """Deterministic offline TTS: a tone whose length tracks the text (≈ 60 ms per character)."""

    name = "scripted"

    def __init__(self, ms_per_char: int = 60, first_chunk_delay_ms: int = 0) -> None:
        self._ms_per_char = ms_per_char
        self.first_chunk_delay_ms = first_chunk_delay_ms
        self.spoken: list[str] = []

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        import asyncio

        self.spoken.append(text)
        if self.first_chunk_delay_ms:
            await asyncio.sleep(self.first_chunk_delay_ms / 1000)
        pcm = tone(max(len(text) * self._ms_per_char, 100)) + silence(80)
        for piece in chunked(pcm):
            yield AudioChunk(pcm=piece)


def synthesis_key(voice: VoiceSpec, text: str, engine: str) -> str:
    raw = f"{engine}|{voice.voice_id}|{voice.language}|{voice.rate}|{voice.style}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()


class CachingTts:
    """LRU cache in front of a provider (backchannels and common lines). ``synthesis_cache`` holds the durable copy."""

    def __init__(self, inner: TtsProvider, limit: int = 512) -> None:
        self.inner = inner
        self.name = inner.name
        self._limit = limit
        self._cache: OrderedDict[str, list[AudioChunk]] = OrderedDict()
        self.hits = 0

    async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
        key = synthesis_key(voice, text, self.inner.name)
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            self._cache.move_to_end(key)
            for chunk in cached:
                yield chunk
            return
        collected: list[AudioChunk] = []
        async for chunk in self.inner.stream(text, voice):
            collected.append(chunk)
            yield chunk
        self._cache[key] = collected
        if len(self._cache) > self._limit:
            self._cache.popitem(last=False)
