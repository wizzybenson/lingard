"""Voice clone providers (SPEC §13.7): voicebox self-hosted primary, ElevenLabs fallback, one interface.

Clones persist across sessions and are deleted only on explicit learner request (cascade lives in the API).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from lingard_pronunciation.audio import pcm_to_wav


class CloneError(RuntimeError):
    pass


class VoiceCloneProvider(Protocol):
    name: str

    async def create(self, user_ref: str, sample_pcm: bytes) -> str:
        """Returns the provider's profile id."""
        ...

    async def delete(self, profile_id: str) -> None:
        """Idempotent: deleting a missing profile is not an error."""
        ...

    async def exists(self, profile_id: str) -> bool: ...


class VoiceboxClone:
    name = "voicebox"

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base, self._timeout = base_url.rstrip("/"), timeout

    async def create(self, user_ref: str, sample_pcm: bytes) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base}/profiles",
                data={"name": f"lingard-{user_ref}"},
                files={"audio": ("sample.wav", pcm_to_wav(sample_pcm), "audio/wav")},
            )
            response.raise_for_status()
            return str(response.json()["id"])

    async def delete(self, profile_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(f"{self._base}/profiles/{profile_id}")
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()

    async def exists(self, profile_id: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return (await client.get(f"{self._base}/profiles/{profile_id}")).status_code == 200


class ElevenLabsClone:
    name = "elevenlabs"
    BASE = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self._headers, self._timeout = {"xi-api-key": api_key}, timeout

    async def create(self, user_ref: str, sample_pcm: bytes) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self.BASE}/voices/add",
                headers=self._headers,
                data={"name": f"lingard-{user_ref}"},
                files={"files": ("sample.wav", pcm_to_wav(sample_pcm), "audio/wav")},
            )
            response.raise_for_status()
            return str(response.json()["voice_id"])

    async def delete(self, profile_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(f"{self.BASE}/voices/{profile_id}", headers=self._headers)
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()

    async def exists(self, profile_id: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return (await client.get(f"{self.BASE}/voices/{profile_id}", headers=self._headers)).status_code == 200


@dataclass
class FakeClone:
    """Offline provider for tests; records calls so deletion cascades can be verified."""

    name: str = "fake"
    profiles: dict[str, bytes] = field(default_factory=dict)
    fail_create: bool = False

    async def create(self, user_ref: str, sample_pcm: bytes) -> str:
        if self.fail_create:
            raise CloneError("provider unavailable")
        profile_id = f"{self.name}-{user_ref}-{len(self.profiles)}"
        self.profiles[profile_id] = sample_pcm
        return profile_id

    async def delete(self, profile_id: str) -> None:
        self.profiles.pop(profile_id, None)

    async def exists(self, profile_id: str) -> bool:
        return profile_id in self.profiles


async def create_with_fallback(
    primary: VoiceCloneProvider, fallback: VoiceCloneProvider | None, user_ref: str, sample_pcm: bytes
) -> tuple[str, str]:
    """(provider name, profile id)."""
    try:
        return primary.name, await primary.create(user_ref, sample_pcm)
    except Exception as exc:
        if fallback is None:
            raise CloneError(str(exc)) from exc
        return fallback.name, await fallback.create(user_ref, sample_pcm)
