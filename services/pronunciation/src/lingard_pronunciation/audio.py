"""WAV helpers for provider uploads (16-bit mono PCM)."""

from __future__ import annotations

import io
import wave


def pcm_to_wav(pcm: bytes, rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def wav_to_pcm(data: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(data)) as wav:
        return wav.readframes(wav.getnframes()), wav.getframerate()
