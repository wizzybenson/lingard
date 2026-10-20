from collections.abc import Callable
from pathlib import Path

from lingard_api.routes.speech import decode_audio


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
