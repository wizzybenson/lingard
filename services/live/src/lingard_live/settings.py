"""Live worker settings and provider wiring (fallbacks on every external provider, SPEC §24)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from lingard_live.stt import DeepgramStt, ElevenLabsStt, FallbackStt, OpenAIStt, SttProvider, VoiceboxStt
from lingard_live.stt_stream import ElevenLabsRealtimeStt, StreamingStt
from lingard_live.tts import CachingTts, ElevenLabsTts, FallbackTts, OpenAITts, TtsProvider, VoiceboxTts
from lingard_live.voices import load_accents, load_overrides

REPO_ROOT = Path(__file__).resolve().parents[4]


class LiveSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_parse_none_str="")

    redis_url: str = "redis://localhost:56379/0"
    livekit_url: str = "ws://localhost:57880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: SecretStr = SecretStr("secret")
    content_root: Path = REPO_ROOT / "content"
    prompts_root: Path = REPO_ROOT / "prompts"
    llm_config: Path = REPO_ROOT / "config" / "llm.yaml"
    voices_config: Path = REPO_ROOT / "config" / "voices.yaml"
    voicebox_url: str | None = None
    openai_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    stt_order: Annotated[list[str], NoDecode] = ["voicebox", "deepgram", "elevenlabs", "openai"]
    """Preference order; providers without a key or URL are skipped, the rest become the fallback chain."""
    tts_order: Annotated[list[str], NoDecode] = ["voicebox", "elevenlabs", "openai"]

    @field_validator("stt_order", "tts_order", mode="before")
    @classmethod
    def _vendor_list(cls, value: object) -> object:
        """A JSON list (as in ``.env``) or a plain comma-separated one: a shell that exported ``.env`` strips the
        quotes, which turned ``["voicebox","openai"]`` into invalid JSON and every request needing voice into a 500."""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [v.strip(" []\"'") for v in value.split(",") if v.strip(" []\"'")]

    voicebox_stt_model: str = "whisper-turbo"
    deepgram_stt_model: str = "nova-3"
    openai_stt_model: str = "gpt-4o-transcribe"
    elevenlabs_stt_model: str = "scribe_v2"
    tts_timeout_s: float = 10.0
    """Per request: short for live replies; lesson narration, which nobody waits on mid-sentence, sets more."""
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    openai_tts_model: str = "gpt-4o-mini-tts"
    claim_check: bool = True
    """Contract Guard claim check on the ``guard`` LLM tier (decision 0012)."""
    claim_check_deadline_s: float = 2.5
    """A check slower than this withholds its sentence."""
    claim_check_context_lines: int = 8
    """Recent lines per speaker the check sees."""
    claim_free_words: int = 6
    """Sentences up to this many words (or questions) made only of grounded words skip the check."""
    filler_after_ms: float | None = 150
    """Say a hesitation if the first sentence is still being checked this long after it is ready; empty = never."""
    stt_streaming: bool = True
    """Transcribe while the learner speaks (ElevenLabs Scribe Realtime, when its key is set); batch is the fallback."""
    elevenlabs_realtime_stt_model: str = "scribe_v2_realtime"


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value else None


def stt_providers(settings: LiveSettings) -> dict[str, SttProvider]:
    """Every speech-to-text provider that has a key or URL, in preference order."""
    available: dict[str, SttProvider] = {}
    if settings.voicebox_url:
        available["voicebox"] = VoiceboxStt(settings.voicebox_url, settings.voicebox_stt_model)
    if key := _secret(settings.deepgram_api_key):
        available["deepgram"] = DeepgramStt(key, settings.deepgram_stt_model)
    if key := _secret(settings.openai_api_key):
        available["openai"] = OpenAIStt(key, settings.openai_stt_model)
    if key := _secret(settings.elevenlabs_api_key):
        available["elevenlabs"] = ElevenLabsStt(key, settings.elevenlabs_stt_model)
    return {name: available[name] for name in settings.stt_order if name in available}


def build_streaming_stt(settings: LiveSettings) -> StreamingStt | None:
    key = _secret(settings.elevenlabs_api_key)
    if not settings.stt_streaming or not key:
        return None
    return ElevenLabsRealtimeStt(key, settings.elevenlabs_realtime_stt_model)


STREAMING_VENDOR = "elevenlabs"
"""The vendor behind ``build_streaming_stt``; the second hearing prefers any other."""


def build_second_ear(settings: LiveSettings) -> SttProvider:
    """The recogniser that hears a streamed turn again before corrections are trusted: another vendor when one is
    configured (its mistakes differ from the streaming model's), the same vendor's batch model otherwise."""
    providers = stt_providers(settings)
    others = [p for name, p in providers.items() if name != STREAMING_VENDOR]
    same = [p for name, p in providers.items() if name == STREAMING_VENDOR]
    return _chain(others + same)


def build_stt(settings: LiveSettings) -> SttProvider:
    return _chain(list(stt_providers(settings).values()))


def _chain(chain: list[SttProvider]) -> SttProvider:
    if not chain:
        raise RuntimeError(
            "no STT provider configured (set VOICEBOX_URL, DEEPGRAM_API_KEY, OPENAI_API_KEY or ELEVENLABS_API_KEY)"
        )
    provider = chain[-1]
    for primary in reversed(chain[:-1]):
        provider = FallbackStt(primary, provider)
    return provider


def tts_providers(settings: LiveSettings) -> dict[str, TtsProvider]:
    """Every text-to-speech provider that has a key or URL, in preference order."""
    available: dict[str, TtsProvider] = {}
    if settings.voicebox_url:
        available["voicebox"] = VoiceboxTts(settings.voicebox_url)
    overrides = load_overrides(settings.voices_config)
    if key := _secret(settings.elevenlabs_api_key):
        available["elevenlabs"] = ElevenLabsTts(
            key,
            settings.elevenlabs_tts_model,
            voices=overrides.get("elevenlabs"),
            timeout=settings.tts_timeout_s,
            accents=load_accents(settings.voices_config),
        )
    if key := _secret(settings.openai_api_key):
        available["openai"] = OpenAITts(
            key, settings.openai_tts_model, voices=overrides.get("openai"), timeout=settings.tts_timeout_s
        )
    return {name: available[name] for name in settings.tts_order if name in available}


def build_tts(settings: LiveSettings) -> TtsProvider:
    chain = list(tts_providers(settings).values())
    if not chain:
        raise RuntimeError("no TTS provider configured (set VOICEBOX_URL, ELEVENLABS_API_KEY or OPENAI_API_KEY)")
    provider = chain[-1]
    for primary in reversed(chain[:-1]):
        provider = FallbackTts(primary, provider)
    return CachingTts(provider)
