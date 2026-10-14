"""Golden self (SPEC §13.3): native TTS renders the line, voice conversion maps it into the learner's timbre.

Zero-shot cloning would copy the learner's current accent, so the accent comes from the native render and only the
timbre comes from the learner. Renders are watermarked and cached by (profile, text, engine params).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from lingard_pronunciation import watermark
from lingard_pronunciation.audio import pcm_to_wav, wav_to_pcm

NativeTts = Callable[[str, str], Awaitable[bytes]]
"""(text, accent) → 16 kHz PCM in a native model voice."""


class VoiceConverter(Protocol):
    name: str

    async def convert(self, source_pcm: bytes, target_profile_id: str) -> bytes: ...


class ElevenLabsSpeechToSpeech:
    """ElevenLabs speech-to-speech: re-voices the native render with the learner's cloned voice."""

    name = "elevenlabs-sts"
    URL = "https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}"

    def __init__(self, api_key: str, model: str = "eleven_multilingual_sts_v2", timeout: float = 30.0) -> None:
        self._key, self._model, self._timeout = api_key, model, timeout

    async def convert(self, source_pcm: bytes, target_profile_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self.URL.format(voice_id=target_profile_id),
                params={"output_format": "pcm_16000"},
                headers={"xi-api-key": self._key},
                data={"model_id": self._model},
                files={"audio": ("native.wav", pcm_to_wav(source_pcm), "audio/wav")},
            )
            response.raise_for_status()
            return response.content


class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def put(self, key: str, audio: bytes) -> None: ...


class MemoryCache:
    """Bounded in-process render cache (one service instance; the durable copy belongs in ``synthesis_cache``)."""

    def __init__(self, limit: int = 256) -> None:
        self._limit = limit
        self._items: OrderedDict[str, bytes] = OrderedDict()

    async def get(self, key: str) -> bytes | None:
        if key in self._items:
            self._items.move_to_end(key)
        return self._items.get(key)

    async def put(self, key: str, audio: bytes) -> None:
        self._items[key] = audio
        self._items.move_to_end(key)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)


@dataclass(frozen=True)
class GoldenRender:
    pcm: bytes
    cache_key: str
    cached: bool


def cache_key(profile_id: str, text: str, accent: str, engine: str) -> str:
    return hashlib.sha256(f"{profile_id}|{accent}|{engine}|{text}".encode()).hexdigest()


class GoldenSelf:
    def __init__(self, native_tts: NativeTts | None, converter: VoiceConverter, cache: CacheBackend) -> None:
        self._tts, self._converter, self._cache = native_tts, converter, cache

    async def render(
        self, text: str, *, accent: str, profile_id: str, user_id: str, native: bytes | None = None
    ) -> GoldenRender:
        """``native`` is a native-speaker render supplied by the caller; without it the configured TTS renders one."""
        key = cache_key(profile_id, text, accent, self._converter.name)
        cached = await self._cache.get(key)
        if cached is not None:
            return GoldenRender(cached, key, True)
        if native is None:
            if self._tts is None:
                raise ValueError("no native render supplied and no native TTS configured")
            native = await self._tts(text, accent)
        converted = await self._converter.convert(native, profile_id)
        if converted[:4] == b"RIFF":
            converted, _ = wav_to_pcm(converted)
        marked = watermark.embed(converted, f"lingard:{user_id}")
        await self._cache.put(key, marked)
        return GoldenRender(marked, key, False)
