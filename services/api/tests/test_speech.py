from collections.abc import Callable
from pathlib import Path

from lingard_api.routes.speech import decode_audio

CONTENT = Path(__file__).resolve().parents[3] / "content"


def test_decode_phone_recording_to_16k_pcm(m4a: Callable[[float], bytes]) -> None:
    pcm = decode_audio(m4a(1.0))
    seconds = len(pcm) / 2 / 16_000
    assert 0.9 <= seconds <= 1.2


def test_corrupt_audio_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        decode_audio(b"not audio at all")


CONTENT = Path(__file__).resolve().parents[3] / "content"


def test_listening_scripts_split_into_speakers() -> None:
    from lingard_api.routes.speech import script_turns, speaker_voice

    script = "F1: Good morning, how can I help?\nM1: I'd like to join the gym.\nIt's for my son.\nF1: Of course."
    assert script_turns(script) == [
        ("F1", "Good morning, how can I help?"),
        ("M1", "I'd like to join the gym. It's for my son."),
        ("F1", "Of course."),
    ]
    assert script_turns("Attention please, platform two.") == [(None, "Attention please, platform two.")]
    french = "F1 : Bonjour.\nM1 : Désolé, c'est complet."  # French typography puts a space before the colon
    assert script_turns(french) == [("F1", "Bonjour."), ("M1", "Désolé, c'est complet.")]
    assert speaker_voice("en", "F2", "en_f_narrator") == "en_f_speaker2"
    assert speaker_voice("fr", "M", "fr_f_narrator") == "fr_m_speaker1"
    assert speaker_voice("fr", None, "fr_f_narrator") == "fr_f_narrator"


async def test_narration_is_rendered_once_then_cached() -> None:
    from collections.abc import AsyncIterator
    from types import SimpleNamespace

    from lingard_api.routes.speech import narrate
    from lingard_contracts.live import AudioChunk
    from lingard_live.tts import VoiceSpec
    from lingard_storage import MemoryObjectStore

    class Recorder:
        def __init__(self) -> None:
            self.voices: list[str] = []

        async def stream(self, text: str, voice: VoiceSpec) -> AsyncIterator[AudioChunk]:
            self.voices.append(voice.voice_id)
            yield AudioChunk(pcm=b"\x01\x00" * 10)

    tts = Recorder()
    state = SimpleNamespace(tts=tts, objects=MemoryObjectStore(), settings=SimpleNamespace(content_root=CONTENT))
    first = await narrate(state, "F1: Bonjour.\nM1: Bonjour madame.", "fr")  # type: ignore[arg-type]
    again = await narrate(state, "F1: Bonjour.\nM1: Bonjour madame.", "fr")  # type: ignore[arg-type]
    assert first == again and tts.voices == ["fr_f_speaker1", "fr_m_speaker1"], "the second play is free"
    assert len(first) > 40, "a pause sits between the two speakers"


def test_audio_answers_byte_ranges_as_ios_asks_for_them() -> None:
    """iOS's player requests a range before playing; a whole file in reply left it buffering in silence."""
    from starlette.requests import Request

    from lingard_api.routes.speech import wav_response
    from lingard_live.audio import pcm_to_wav

    pcm = bytes(range(256)) * 40
    wav = pcm_to_wav(pcm)

    def ask(value: str | None) -> Request:
        headers = [(b"range", value.encode())] if value else []
        return Request({"type": "http", "method": "GET", "headers": headers})

    whole = wav_response(pcm, ask(None))
    assert whole.status_code == 200 and whole.body == wav and whole.headers["accept-ranges"] == "bytes"
    probe = wav_response(pcm, ask("bytes=0-1"))
    assert probe.status_code == 206 and probe.body == wav[:2]
    assert probe.headers["content-range"] == f"bytes 0-1/{len(wav)}"
    assert wav_response(pcm, ask("bytes=100-")).body == wav[100:]
    assert wav_response(pcm, ask("bytes=-10")).body == wav[-10:]
    assert wav_response(pcm, ask(f"bytes={len(wav)}-")).status_code == 416


async def test_lesson_audio_renders_a_few_at_a_time_and_retries_once() -> None:
    """A lesson asked for every recording at once; the provider answered 429 and the learner saw a server error."""
    import asyncio
    from types import SimpleNamespace

    from lingard_api.routes import speech
    from lingard_contracts.live import AudioChunk

    class Store:
        def __init__(self) -> None:
            self.saved: dict[str, bytes] = {}

        async def get(self, bucket: str, key: str) -> bytes:
            return self.saved[key]

        async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
            self.saved[key] = data

    class Tts:
        def __init__(self) -> None:
            self.now = self.most = self.calls = 0

        async def stream(self, text: str, voice: object):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("429 Too Many Requests")
            self.now += 1
            self.most = max(self.most, self.now)
            await asyncio.sleep(0.02)
            self.now -= 1
            yield AudioChunk(pcm=b"\x00\x00" * 8)

    tts = Tts()
    root = CONTENT
    state = SimpleNamespace(tts=tts, objects=Store(), settings=SimpleNamespace(content_root=root))
    lines = [f"Phrase {i}." for i in range(6)] + ["Phrase 0."] * 3
    audio = await asyncio.gather(*(speech.narrate(state, line, "fr") for line in lines))  # type: ignore[arg-type]
    assert all(audio) and tts.most <= 2, "two renders at a time at most"
    assert tts.calls == 1 + 6, "the failed render is retried; the same line is never rendered twice"
