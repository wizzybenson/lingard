import io
from pathlib import Path

import av
import numpy as np

from lingard_api.routes.speech import decode_audio


def m4a(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=44_100)
        stream.layout = "mono"
        samples = (0.3 * np.sin(2 * np.pi * 220 * np.arange(int(44_100 * seconds)) / 44_100)).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
        frame.sample_rate = 44_100
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return buffer.getvalue()


def test_decode_phone_recording_to_16k_pcm() -> None:
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
