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
    """jamiepine/voicebox's REST API (read from its source at 8af7efe, 2026-10-07; not yet run against a live server
    here): a profile is created empty, then filled with samples of 2–30 s, each with its transcript, which voicebox's
    own ``/transcribe`` supplies. A profile left half-made by a failure is deleted, never kept."""

    name = "voicebox"
    SAMPLE_S = 25
    MIN_SAMPLE_S = 2

    def __init__(
        self, base_url: str, timeout: float = 120.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base, self._timeout, self._transport = base_url.rstrip("/"), timeout, transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=self._timeout, transport=self._transport)

    def _pieces(self, pcm: bytes) -> list[bytes]:
        size, least = self.SAMPLE_S * 16_000 * 2, self.MIN_SAMPLE_S * 16_000 * 2
        pieces = [pcm[i : i + size] for i in range(0, len(pcm), size)]
        if len(pieces) > 1 and len(pieces[-1]) < least:
            pieces[-2] += pieces.pop()  # a 2 s tail joins the piece before it (still under voicebox's 30 s)
        return pieces

    async def create(self, user_ref: str, sample_pcm: bytes) -> str:
        async with self._client() as client:
            response = await client.post("/profiles", json={"name": f"lingard-{user_ref}", "voice_type": "cloned"})
            response.raise_for_status()
            profile_id = str(response.json()["id"])
            try:
                for piece in self._pieces(sample_pcm):
                    audio = ("sample.wav", pcm_to_wav(piece), "audio/wav")
                    heard = await client.post("/transcribe", files={"file": audio})
                    heard.raise_for_status()
                    added = await client.post(
                        f"/profiles/{profile_id}/samples",
                        files={"file": audio},
                        data={"reference_text": str(heard.json()["text"])},
                    )
                    added.raise_for_status()
            except Exception:
                await client.delete(f"/profiles/{profile_id}")
                raise
            return profile_id

    async def delete(self, profile_id: str) -> None:
        async with self._client() as client:
            response = await client.delete(f"/profiles/{profile_id}")
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()

    async def exists(self, profile_id: str) -> bool:
        async with self._client() as client:
            return (await client.get(f"/profiles/{profile_id}")).status_code == 200


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
            if response.is_error:  # e.g. a plan without instant voice cloning: say so, not just "400"
                detail = response.json().get("detail", {}) if "json" in response.headers.get("content-type", "") else {}
                message = detail.get("message", response.text) if isinstance(detail, dict) else str(detail)
                raise CloneError(f"ElevenLabs refused the clone ({response.status_code}): {message}")
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
