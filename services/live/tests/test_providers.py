import functools
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from lingard_live.settings import LiveSettings, build_stt, stt_providers, tts_providers
from lingard_live.stt import DeepgramStt, ElevenLabsStt, FallbackStt
from lingard_live.tts import ElevenLabsTts, VoiceSpec
from lingard_live.voices import OPENAI_VOICES, gender_of, pick

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


def test_speech_models_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "nova-2")
    monkeypatch.setenv("ELEVENLABS_TTS_MODEL", "eleven_turbo_v2_5")
    settings = _settings(deepgram_api_key="d", elevenlabs_api_key="e")
    assert stt_providers(settings)["deepgram"]._model == "nova-2"  # type: ignore[attr-defined]
    assert stt_providers(settings)["elevenlabs"]._model == "scribe_v2", "unset keeps the default"  # type: ignore[attr-defined]
    assert tts_providers(settings)["elevenlabs"]._model == "eleven_turbo_v2_5"  # type: ignore[attr-defined]


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


async def test_elevenlabs_maps_logical_voices_to_account_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    voices = [
        {"voice_id": "v-f1", "labels": {"gender": "female"}},
        {"voice_id": "v-m1", "labels": {"gender": "male"}},
        {"voice_id": "v-m2", "labels": {"gender": "male"}},
    ]
    fetches = []

    def handle(request: httpx.Request) -> httpx.Response:
        fetches.append(request.url.path)
        return httpx.Response(200, json={"voices": voices})

    _fake(monkeypatch, httpx.MockTransport(handle))
    tts = ElevenLabsTts("k", voices={"fr_f_41_chloe": "pinned"})
    martin = await tts.voice_for("fr_m_58_martin")
    assert martin in ("v-m1", "v-m2") and await tts.voice_for("fr_m_58_martin") == martin
    assert await tts.voice_for("fr_f_46_nadia") == "v-f1"
    assert await tts.voice_for("fr_f_41_chloe") == "pinned"
    assert fetches == ["/v1/voices"], "the voice list is fetched once"


async def test_elevenlabs_stream_never_splits_a_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP chunks can end mid-sample; an odd byte count crashed the NPC's first line (2026-10-18)."""
    pcm = bytes(range(200))  # 100 samples
    sizes = [3, 7, 1, 50, 139]  # odd cuts, as the network delivers them

    async def body() -> AsyncIterator[bytes]:
        start = 0
        for size in sizes:
            yield pcm[start : start + size]
            start += size

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/voices":
            return httpx.Response(200, json={"voices": [{"voice_id": "v-f1", "labels": {"gender": "female"}}]})
        return httpx.Response(200, content=body())

    _fake(monkeypatch, httpx.MockTransport(handle))
    chunks = [c.pcm async for c in ElevenLabsTts("k").stream("Bonjour", VoiceSpec("fr_f_41_chloe", "fr"))]
    assert all(len(c) % 2 == 0 and c for c in chunks)
    assert b"".join(chunks) == pcm


def test_openai_voices_follow_gender_and_stay_stable() -> None:
    assert gender_of("en_m_64_ron") == "m" and gender_of("narrator") == "f"
    assert pick(OPENAI_VOICES["m"], "en_m_64_ron") == pick(OPENAI_VOICES["m"], "en_m_64_ron")
    assert pick(OPENAI_VOICES["m"], "en_m_64_ron") in OPENAI_VOICES["m"]


def test_streaming_stt_needs_the_elevenlabs_key_and_can_be_switched_off() -> None:
    from lingard_live.settings import build_streaming_stt

    assert build_streaming_stt(_settings()) is None
    assert build_streaming_stt(_settings(elevenlabs_api_key="e")) is not None
    off = _settings(elevenlabs_api_key="e")
    off.stt_streaming = False
    assert build_streaming_stt(off) is None


async def test_realtime_stream_keeps_a_commit_whose_waiter_was_cancelled() -> None:
    """A fake Scribe: each commit is answered with the next segment after 100 ms. The first ``finish`` (a speculation)
    is cancelled before its answer arrives; the next ``finish`` must still return both segments, in order."""
    import asyncio

    import websockets

    from lingard_live.stt_stream import MIN_COMMIT_BYTES, ElevenLabsStream

    segments = iter(["Oui, je comprends.", "Est-ce que je peux payer ?"])

    async def scribe(ws: websockets.ServerConnection) -> None:
        await ws.send(json.dumps({"message_type": "session_started"}))
        async for raw in ws:
            if json.loads(raw)["commit"]:
                await asyncio.sleep(0.1)
                await ws.send(json.dumps({"message_type": "committed_transcript", "text": next(segments)}))

    async with websockets.serve(scribe, "127.0.0.1", 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        stream = ElevenLabsStream(f"ws://127.0.0.1:{port}", "key", "elevenlabs-realtime")
        audio = b"\x00" * MIN_COMMIT_BYTES
        await stream.feed(audio)
        speculation = asyncio.create_task(stream.finish(2))
        await asyncio.sleep(0.03)
        speculation.cancel()
        await stream.feed(audio)
        final = await stream.finish(2)
        await stream.close()
    assert final.text == "Oui, je comprends. Est-ce que je peux payer ?"


def test_the_second_hearing_prefers_another_vendor_than_the_streaming_one() -> None:
    from lingard_live.settings import build_second_ear

    both = LiveSettings(
        _env_file=None,
        elevenlabs_api_key=SecretStr("e"),
        openai_api_key=SecretStr("o"),
        deepgram_api_key=None,
        voicebox_url=None,
        stt_order=["voicebox", "deepgram", "elevenlabs", "openai"],
    )
    assert build_stt(both).name == "elevenlabs>openai"
    assert build_second_ear(both).name == "openai>elevenlabs"
    alone = both.model_copy(update={"openai_api_key": None})
    assert build_second_ear(alone).name == "elevenlabs", "no other vendor: the batch model still hears it again"
