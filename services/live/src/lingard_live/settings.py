"""Live worker settings and provider wiring (fallbacks on every external provider, SPEC §24)."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from lingard_live.stt import DeepgramStt, ElevenLabsStt, FallbackStt, OpenAIStt, SttProvider, VoiceboxStt
from lingard_live.tts import CachingTts, ElevenLabsTts, FallbackTts, OpenAITts, TtsProvider, VoiceboxTts

REPO_ROOT = Path(__file__).resolve().parents[4]


class LiveSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:56379/0"
    livekit_url: str = "ws://localhost:57880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: SecretStr = SecretStr("secret")
    content_root: Path = REPO_ROOT / "content"
    prompts_root: Path = REPO_ROOT / "prompts"
    llm_config: Path = REPO_ROOT / "config" / "llm.yaml"
    voicebox_url: str | None = None
    openai_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    stt_order: list[str] = ["voicebox", "deepgram", "openai", "elevenlabs"]
    """Preference order; providers without a key or URL are skipped, the rest become the fallback chain."""
    tts_order: list[str] = ["voicebox", "elevenlabs", "openai"]


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value else None


def build_stt(settings: LiveSettings) -> SttProvider:
    available: dict[str, SttProvider] = {}
    if settings.voicebox_url:
        available["voicebox"] = VoiceboxStt(settings.voicebox_url)
    if key := _secret(settings.deepgram_api_key):
        available["deepgram"] = DeepgramStt(key)
    if key := _secret(settings.openai_api_key):
        available["openai"] = OpenAIStt(key)
    if key := _secret(settings.elevenlabs_api_key):
        available["elevenlabs"] = ElevenLabsStt(key)
    chain = [available[name] for name in settings.stt_order if name in available]
    if not chain:
        raise RuntimeError(
            "no STT provider configured (set VOICEBOX_URL, DEEPGRAM_API_KEY, OPENAI_API_KEY or ELEVENLABS_API_KEY)"
        )
    provider = chain[-1]
    for primary in reversed(chain[:-1]):
        provider = FallbackStt(primary, provider)
    return provider


def build_tts(settings: LiveSettings) -> TtsProvider:
    available: dict[str, TtsProvider] = {}
    if settings.voicebox_url:
        available["voicebox"] = VoiceboxTts(settings.voicebox_url)
    if key := _secret(settings.elevenlabs_api_key):
        available["elevenlabs"] = ElevenLabsTts(key)
    if key := _secret(settings.openai_api_key):
        available["openai"] = OpenAITts(key)
    chain = [available[name] for name in settings.tts_order if name in available]
    if not chain:
        raise RuntimeError("no TTS provider configured (set VOICEBOX_URL, ELEVENLABS_API_KEY or OPENAI_API_KEY)")
    provider = chain[-1]
    for primary in reversed(chain[:-1]):
        provider = FallbackTts(primary, provider)
    return CachingTts(provider)
