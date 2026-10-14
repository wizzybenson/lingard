import io

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
