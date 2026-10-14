"""Contract test of ``LiveKitTransport`` against a real local LiveKit server (``docker compose up -d livekit``)."""

import asyncio
import os
import socket
import uuid
from collections.abc import AsyncIterator

import pytest
from livekit import rtc

from lingard_contracts.live import AudioChunk, LearnerSpeechStarted, LearnerTurnEnded, LiveSessionConfig, TurnPolicy
from lingard_live.audio import chunked, silence, tone
from lingard_live.livekit_transport import LiveKitTransport, mint_token

URL = os.environ.get("LIVEKIT_URL", "ws://localhost:57880")
KEY, SECRET = "devkey", "secret"
pytestmark = pytest.mark.integration


def _up() -> bool:
    try:
        with socket.create_connection(("localhost", 57880), timeout=0.5):
            return True
    except OSError:
        return False


async def _learner(room_name: str, identity: str) -> tuple[rtc.Room, rtc.AudioSource]:
    room = rtc.Room()
    await room.connect(URL, mint_token(KEY, SECRET, room_name, identity, agent=False))
    source = rtc.AudioSource(16000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)
    await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    return room, source


async def _say(source: rtc.AudioSource, pcm: bytes) -> None:
    for piece in chunked(pcm, ms=20):
        if len(piece) == 640:
            await source.capture_frame(rtc.AudioFrame(piece, 16000, 1, 320))


@pytest.mark.skipif(not _up(), reason="livekit not running")
async def test_turn_detected_and_npc_audio_reaches_learner() -> None:
    room_name = f"scene-{uuid.uuid4().hex[:8]}"
    user_id = uuid.uuid4()
    learner_room, mic = await _learner(room_name, str(user_id))
    heard: list[int] = []
    listeners: set[asyncio.Task[None]] = set()

    def on_track(track: rtc.Track, *_: object) -> None:
        async def listen() -> None:
            async for event in rtc.AudioStream(track, sample_rate=16000, num_channels=1):
                data = bytes(event.frame.data)
                if any(data):
                    heard.append(len(data))

        if track.kind == rtc.TrackKind.KIND_AUDIO:
            listeners.add(asyncio.create_task(listen()))

    learner_room.on("track_subscribed", on_track)
    session = await LiveKitTransport(URL, KEY, SECRET).open(
        LiveSessionConfig(
            session_id=uuid.uuid4(),
            user_id=user_id,
            scene_id=uuid.uuid4(),
            room=room_name,
            locale="fr-FR",
            policy=TurnPolicy(eot_ms=700),
        )
    )
    events: list[object] = []

    async def collect() -> None:
        async for event in session.events():
            events.append(event)
            if isinstance(event, LearnerTurnEnded):
                return

    collector = asyncio.create_task(collect())
    await asyncio.sleep(1.0)
    await _say(mic, silence(300) + tone(900, 180, 9000) + silence(1200))
    await asyncio.wait_for(collector, timeout=10)
    assert any(isinstance(e, LearnerSpeechStarted) for e in events)
    ended = next(e for e in events if isinstance(e, LearnerTurnEnded))
    assert 600 <= ended.speech_end_ms - ended.speech_start_ms <= 1300

    async def npc_audio() -> AsyncIterator[AudioChunk]:
        for piece in chunked(tone(800, 300, 8000), ms=20):
            yield AudioChunk(pcm=piece)

    await session.speak(npc_audio(), "u1")
    await asyncio.sleep(1.0)
    assert sum(heard) > 16000, "learner should receive most of the NPC's 800 ms"
    await session.close()
    await learner_room.disconnect()
