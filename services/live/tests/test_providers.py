import functools
import json

import httpx
import pytest
from pydantic import SecretStr

from lingard_live.settings import LiveSettings, build_stt
from lingard_live.stt import DeepgramStt, ElevenLabsStt, FallbackStt

PCM = b"\x00\x01" * 1600


def _settings(**keys: str) -> LiveSettings:
    secrets = {k: SecretStr(v) for k, v in keys.items() if k.endswith("_key")}
    return LiveSettings(_env_file=None, **{**keys, **secrets})  # type: ignore[arg-type]


def _chain(provider: object) -> list[str]:
    names = []
    while isinstance(provider, FallbackStt):
        names.append(provider.primary.name)
        provider = provider.fallback
    return [*names, provider.name]  # type: ignore[attr-defined]


def test_stt_chain_uses_only_configured_providers_in_preference_order() -> None:
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        build_stt(_settings())
    assert _chain(build_stt(_settings(elevenlabs_api_key="e"))) == ["elevenlabs"]
    assert _chain(build_stt(_settings(elevenlabs_api_key="e", deepgram_api_key="d"))) == ["deepgram", "elevenlabs"]
    custom = _settings(openai_api_key="o", deepgram_api_key="d")
    custom.stt_order = ["openai", "deepgram"]
    assert _chain(build_stt(custom)) == ["openai", "deepgram"]


def _fake(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=handler))


async def test_deepgram_sends_wav_and_reads_the_best_alternative(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(params=dict(request.url.params), auth=request.headers["authorization"], body=request.content[:4])
        alternative = {"transcript": " Bonjour ", "confidence": 0.93}
        return httpx.Response(200, json={"results": {"channels": [{"alternatives": [alternative]}]}})

    _fake(monkeypatch, httpx.MockTransport(handle))
    result = await DeepgramStt("dg-key").transcribe(PCM, "fr-FR")
    assert (result.text, result.confidence, result.provider) == ("Bonjour", 0.93, "deepgram")
    assert seen == {
        "params": {"model": "nova-3", "language": "fr", "smart_format": "true"},
        "auth": "Token dg-key",
        "body": b"RIFF",
    }


async def test_elevenlabs_scribe_sends_raw_pcm(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        body = request.content
        seen.update(key=request.headers["xi-api-key"], pcm=b'name="file_format"\r\n\r\npcm_s16le_16' in body)
        seen["model"] = b'name="model_id"\r\n\r\nscribe_v2' in body
        return httpx.Response(200, content=json.dumps({"text": "Hello there", "language_probability": 0.99}))

    _fake(monkeypatch, httpx.MockTransport(handle))
    result = await ElevenLabsStt("el-key").transcribe(PCM, "en-GB")
    assert (result.text, result.confidence, result.provider) == ("Hello there", None, "elevenlabs")
    assert seen == {"key": "el-key", "pcm": True, "model": True}
