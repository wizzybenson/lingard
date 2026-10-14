"""``VoiceTransport`` over a self-hosted LiveKit server (decision 0001).

The worker joins the learner's room as a hidden-from-UI agent participant, subscribes to the learner's microphone at
16 kHz mono, runs our ``Endpointer`` on it (turn-taking stays ours, SPEC §6.2) and publishes NPC audio on a track.
WebRTC supplies echo cancellation, jitter buffering and loss recovery on iOS, Android and web.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import timedelta

from livekit import api, rtc

from lingard_contracts.live import (
    SAMPLE_RATE,
    AudioChunk,
    BargeIn,
    Closed,
    LiveEvent,
    LiveSessionConfig,
    NetworkDegraded,
    TurnPolicy,
)
from lingard_live.vad import FRAME_MS, Endpointer

logger = logging.getLogger(__name__)
AGENT_IDENTITY = "lingard-npc"


def mint_token(api_key: str, api_secret: str, room: str, identity: str, *, agent: bool, ttl_minutes: int = 60) -> str:
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, agent=agent or None)
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=ttl_minutes))
        .to_jwt()
    )


class LiveKitSession:
    def __init__(self, room: rtc.Room, source: rtc.AudioSource, policy: TurnPolicy, learner_identity: str) -> None:
        self._room = room
        self._source = source
        self._endpointer = Endpointer(policy=policy)
        self._learner = learner_identity
        self._queue: asyncio.Queue[LiveEvent] = asyncio.Queue()
        self._readers: set[asyncio.Task[None]] = set()
        self._speaking: str | None = None
        room.on("track_subscribed", self._on_track)
        room.on("disconnected", lambda *_: self._queue.put_nowait(Closed(reason="disconnected")))
        room.on("connection_quality_changed", self._on_quality)
        for participant in room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track is not None:
                    self._on_track(publication.track, publication, participant)

    def _on_quality(self, participant: rtc.Participant, quality: rtc.ConnectionQuality) -> None:
        if participant.identity == self._learner and quality == rtc.ConnectionQuality.QUALITY_POOR:
            self._queue.put_nowait(NetworkDegraded(detail="learner connection poor"))

    def _on_track(
        self, track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO or participant.identity != self._learner:
            return
        task = asyncio.create_task(
            self._read(rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1, frame_size_ms=FRAME_MS))
        )
        self._readers.add(task)
        task.add_done_callback(self._readers.discard)

    async def _read(self, stream: rtc.AudioStream) -> None:
        async for event in stream:
            for live_event in self._endpointer.feed(bytes(event.frame.data)):
                if isinstance(live_event, BargeIn) and self._speaking:
                    live_event = BargeIn(utterance_id=self._speaking, at_ms=live_event.at_ms)
                self._queue.put_nowait(live_event)

    async def events(self) -> AsyncIterator[LiveEvent]:
        while True:
            event = await self._queue.get()
            yield event
            if isinstance(event, Closed):
                return

    async def speak(self, stream: AsyncIterator[AudioChunk], utterance_id: str) -> None:
        self._speaking = utterance_id
        self._endpointer.npc_started(utterance_id)
        try:
            async for chunk in stream:
                if self._speaking != utterance_id:
                    break
                samples = len(chunk.pcm) // 2
                frame = rtc.AudioFrame(chunk.pcm, chunk.sample_rate, 1, samples)
                await self._source.capture_frame(frame)
            if self._speaking == utterance_id:
                await self._source.wait_for_playout()
        finally:
            if self._speaking == utterance_id:
                self._speaking = None
                self._endpointer.npc_finished()

    async def cancel_speech(self, utterance_id: str) -> None:
        if self._speaking == utterance_id or utterance_id == "any":
            self._speaking = None
            self._source.clear_queue()
            self._endpointer.npc_finished()

    async def set_turn_policy(self, policy: TurnPolicy) -> None:
        self._endpointer.policy = policy

    async def caption(self, speaker: str, text: str) -> None:
        payload = json.dumps({"type": "caption", "speaker": speaker, "text": text}).encode()
        await self._room.local_participant.publish_data(payload, reliable=True, topic="captions")

    async def close(self) -> None:
        for task in list(self._readers):
            task.cancel()
        await self._source.aclose()
        await self._room.disconnect()


class LiveKitTransport:
    def __init__(self, url: str, api_key: str, api_secret: str) -> None:
        self._url, self._key, self._secret = url, api_key, api_secret

    async def open(self, cfg: LiveSessionConfig) -> LiveKitSession:
        room = rtc.Room()
        token = mint_token(self._key, self._secret, cfg.room, AGENT_IDENTITY, agent=True)
        await room.connect(self._url, token, rtc.RoomOptions(auto_subscribe=True))
        source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=2000)
        track = rtc.LocalAudioTrack.create_audio_track("npc-voice", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(track, options)
        return LiveKitSession(room, source, cfg.policy, learner_identity=str(cfg.user_id))
