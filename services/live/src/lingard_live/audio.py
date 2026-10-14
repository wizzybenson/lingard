"""PCM helpers: 16-bit mono PCM is the live plane's interchange format."""

from __future__ import annotations

import io
import wave

import numpy as np

from lingard_contracts.live import SAMPLE_RATE


def resample(pcm: bytes, src_rate: int, dst_rate: int = SAMPLE_RATE) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    duration = samples.size / src_rate
    target = max(round(duration * dst_rate), 1)
    positions = np.linspace(0, samples.size - 1, target)
    return np.interp(positions, np.arange(samples.size), samples).astype(np.int16).tobytes()


def wav_to_pcm(data: bytes, dst_rate: int = SAMPLE_RATE) -> bytes:
    with wave.open(io.BytesIO(data)) as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("only 16-bit WAV is supported")
    samples = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return resample(samples.tobytes(), rate, dst_rate)


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def tone(ms: int, freq: float = 220.0, amplitude: int = 6000, rate: int = SAMPLE_RATE) -> bytes:
    t = np.arange(int(rate * ms / 1000)) / rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()


def silence(ms: int, rate: int = SAMPLE_RATE) -> bytes:
    return b"\x00\x00" * int(rate * ms / 1000)


def chunked(pcm: bytes, ms: int = 100, rate: int = SAMPLE_RATE) -> list[bytes]:
    size = rate * ms // 1000 * 2
    return [pcm[i : i + size] for i in range(0, len(pcm), size)]
