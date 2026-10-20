"""A robot learner that uses the running stack exactly as the app does: signs in over HTTP, plays a scene in a real
LiveKit room with spoken audio (macOS ``say``, a different engine from the NPC voices), lets an LLM decide what to say
next, ends the day and waits for the night notebook. ``--clone`` also enrols a voice clone with consent, fetches the
golden-self reference, scores a shadowing attempt and deletes the clone again (verified by the API).

Paid: a day plan if none is waiting, a few NPC turns, the night pass, and (with ``--clone``) one clone and one
speech-to-speech render. Needs the API, both workers, LiveKit and (for ``--clone``) the pronunciation service.

    uv run python -m tools.voicebench.e2e_learner --city rivemont --turns 4 [--scene <id>] [--clone]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from livekit import rtc

from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_SCALE
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry

ROOT = Path(__file__).resolve().parents[2]
RATE = 16_000
FRAME = RATE // 100  # 10 ms
SAY_VOICES = {"fr": "Eddy (French (Canada))", "en": "Eddy (English (UK))"}
LANGUAGE_NAMES = {"fr": "French", "en": "English"}
SILENCE_RMS = 300
"""int16 RMS under which a 10 ms NPC frame counts as silence."""
NPC_DONE_MS = 1500
"""The NPC has finished its reply after this much silence following speech."""
CLONE_TEXT = {
    "fr": (
        "Bonjour, je m'appelle Sam et j'habite à Rivemont depuis quelques mois. Le matin, je prends le bus pour aller "
        "au travail, puis je m'arrête souvent au marché pour acheter du pain et des fruits. Le week-end, j'aime me "
        "promener au bord de l'eau avec des amis, et parfois nous allons au cinéma. J'apprends le français parce que "
        "je veux m'installer au Canada et trouver un bon emploi. Ce n'est pas toujours facile, mais je fais des "
        "progrès chaque semaine."
    ),
    "en": (
        "Hello, my name is Sam and I have been living in Ashford for a few months. In the morning I take the bus to "
        "work, and on the way home I often stop at the market to buy bread and fruit. At the weekend I like walking "
        "by the river with friends, and sometimes we go to the cinema. I am learning English because I want to move "
        "abroad and find a good job. It is not always easy, but I am making progress every week."
    ),
}


def say(text: str, language: str) -> bytes:
    """16 kHz mono int16 PCM of ``text`` spoken by a macOS system voice."""
    with tempfile.TemporaryDirectory() as tmp:
        aiff, raw = Path(tmp) / "say.aiff", Path(tmp) / "say.raw"
        # Fixed local tools (macOS say, ffmpeg) with argument lists, never a shell.
        subprocess.run(["say", "-v", SAY_VOICES[language], "-o", str(aiff), text], check=True)  # noqa: S603, S607
        convert = ["ffmpeg", "-loglevel", "error", "-i", str(aiff), "-ac", "1", "-ar", str(RATE), "-f", "s16le"]
        subprocess.run([*convert, str(raw)], check=True)  # noqa: S603
        return raw.read_bytes()


def wav(pcm: bytes) -> bytes:
    with tempfile.TemporaryFile() as handle:
        with wave.open(handle, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(pcm)
        handle.seek(0)
        return handle.read()


def rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


@dataclass
class Room:
    """The learner's side of a LiveKit room: a microphone track and the NPC's audio and captions."""

    room: rtc.Room
    mic: rtc.AudioSource
    captions: list[tuple[float, str, str]] = field(default_factory=list)
    npc_audio: bytearray = field(default_factory=bytearray)
    last_voiced: float = 0.0
    first_voiced_after: dict[float, float] = field(default_factory=dict)
    readers: set[asyncio.Task[None]] = field(default_factory=set)

    @classmethod
    async def join(cls, url: str, token: str) -> Room:
        room = rtc.Room()
        mic = rtc.AudioSource(RATE, 1, queue_size_ms=1000)
        self = cls(room, mic)
        room.on("track_subscribed", self._on_track)
        room.on("data_received", self._on_data)
        await room.connect(url, token, rtc.RoomOptions(auto_subscribe=True))
        track = rtc.LocalAudioTrack.create_audio_track("mic", mic)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        return self

    def _on_track(self, track: rtc.Track, *_: Any) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            task = asyncio.create_task(self._listen(rtc.AudioStream(track, sample_rate=RATE, num_channels=1)))
            self.readers.add(task)

    async def _listen(self, stream: rtc.AudioStream) -> None:
        async for event in stream:
            pcm = bytes(event.frame.data)
            self.npc_audio.extend(pcm)
            if rms(pcm) > SILENCE_RMS:
                now = time.monotonic()
                self.last_voiced = now
                for mark, first in list(self.first_voiced_after.items()):
                    if first == 0.0 and now > mark:
                        self.first_voiced_after[mark] = now

    def _on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic == "captions":
            body = json.loads(packet.data)
            self.captions.append((time.monotonic(), body.get("speaker", ""), body.get("text", "")))

    async def speak(self, pcm: bytes) -> float:
        """Plays ``pcm`` into the microphone at real time; returns when the last voiced sample went out."""
        for offset in range(0, len(pcm), FRAME * 2):
            chunk = pcm[offset : offset + FRAME * 2].ljust(FRAME * 2, b"\x00")
            await self.mic.capture_frame(rtc.AudioFrame(chunk, RATE, 1, FRAME))
        await self.mic.wait_for_playout()
        return time.monotonic()

    async def silence_until_npc_done(self, since: float, timeout_s: float = 30.0) -> bool:
        """Feeds microphone silence (as a real open mic does) until the NPC spoke after ``since`` and went quiet."""
        quiet = b"\x00\x00" * FRAME
        deadline = since + timeout_s
        while time.monotonic() < deadline:
            await self.mic.capture_frame(rtc.AudioFrame(quiet, RATE, 1, FRAME))
            spoke = self.last_voiced > since
            if spoke and (time.monotonic() - self.last_voiced) * 1000 > NPC_DONE_MS:
                return True
        return False

    async def leave(self) -> None:
        for task in self.readers:
            task.cancel()
        await self.room.disconnect()


class Api:
    def __init__(self, base: str) -> None:
        self.http = httpx.AsyncClient(base_url=base, timeout=60.0)

    async def sign_in(self) -> None:
        body = {
            "display_name": os.environ["LINGARD_TEST_NAME"],
            "pin": os.environ["LINGARD_TEST_PIN"],
            "device_label": "e2e robot",
        }
        token = (await self.http.post("/v1/auth/sign-in", json=body)).raise_for_status().json()["access_token"]
        self.http.headers["Authorization"] = f"Bearer {token}"

    async def get(self, path: str, **params: Any) -> Any:
        return (await self.http.get(path, params=params)).raise_for_status().json()

    async def post(self, path: str, body: Any = None) -> Any:
        response = (await self.http.post(path, json=body)).raise_for_status()
        return response.json() if response.content else None


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


async def ready_scene(api: Api, city: str) -> tuple[str, str]:
    """(session id, first playable scene id) of the day to play, planning one if none is waiting."""
    started = time.monotonic()
    day = await api.post("/v1/sessions", {"city": city})
    while day["status"] == "planning" or not day["scene_ids"]:
        if day["status"] == "failed":
            raise RuntimeError(f"day planning failed: {day.get('error')}")
        await asyncio.sleep(2)
        day = await api.get(f"/v1/sessions/{day['id']}")
    log(f"day {day['id']} ready in {time.monotonic() - started:.1f}s with {len(day['scene_ids'])} scene(s)")
    for scene_id in day["scene_ids"]:
        if (await api.get(f"/v1/scenes/{scene_id}"))["status"] == "planned":
            return day["id"], scene_id
    return day["id"], day["scene_ids"][0]


async def play(api: Api, scene_id: str, turns: int, out: Path) -> list[dict[str, Any]]:
    scene = await api.get(f"/v1/scenes/{scene_id}")
    language = CITY_LANGUAGE[scene["city"]]
    log(f"scene at {scene['location_name']} with {scene['npc_name']} ({scene['npc_role']})")
    log(f"goal: {scene['learner_goal']}")
    asked = time.monotonic()
    ticket = await api.post(f"/v1/scenes/{scene_id}/live")
    room = await Room.join(ticket["livekit_url"], ticket["token"])
    room.first_voiced_after[asked] = 0.0
    log(f"joined {ticket['room']} {time.monotonic() - asked:.2f}s after asking to go live")

    prompts = PromptRegistry(ROOT / "prompts")
    router = LLMRouter(LLMConfig.load(ROOT / "config" / "llm.yaml"))
    learner_prompt = prompts.get("sim_learner")
    band = scene.get("learner_band") or 5
    system = learner_prompt.render(
        scale_name=LANGUAGE_SCALE[language],
        band=band,
        language_name=LANGUAGE_NAMES[language],
        npc_name=scene["npc_name"],
        goal=scene["learner_goal"],
        weaknesses="agreement, prepositions",
    )
    history: list[BaseMessage] = []
    turns_out: list[dict[str, Any]] = []
    if not await room.silence_until_npc_done(asked, timeout_s=40):
        log("no opening line from the NPC within 40 s")
    else:
        log(f"opening audio {room.first_voiced_after.pop(asked) - asked:.2f}s after asking to go live")
    for n in range(turns):
        npc_said = " ".join(text for _, speaker, text in room.captions if speaker != "learner") or "(silence)"
        heard = [text for _, speaker, text in room.captions if speaker != "learner"]
        history.append(HumanMessage(content=heard[-1] if heard else npc_said))
        line = await router.text("mid", learner_prompt, router.messages("mid", system, "", history)[:-1] + history[-1:])
        history.append(AIMessage(content=line))
        pcm = say(line, language)
        captions_before = len(room.captions)
        log(f"learner ({len(pcm) / 2 / RATE:.1f}s): {line}")
        ended = await room.speak(pcm)
        room.first_voiced_after[ended] = 0.0
        done = await room.silence_until_npc_done(ended)
        first = room.first_voiced_after.pop(ended)
        new = room.captions[captions_before:]
        heard_back = next((text for _, speaker, text in new if speaker == "learner"), "")
        npc = " ".join(text for _, speaker, text in new if speaker != "learner")
        first_caption = next((t for t, speaker, _ in new if speaker != "learner"), 0.0)
        result = {
            "turn": n + 1,
            "said": line,
            "transcribed": heard_back,
            "npc": npc,
            "first_audio_s": round(first - ended, 2) if first else None,
            "first_caption_s": round(first_caption - ended, 2) if first_caption else None,
            "replied": done,
        }
        turns_out.append(result)
        log(f"  heard as: {heard_back}")
        log(f"  npc: {npc}")
        log(f"  first NPC audio {result['first_audio_s']}s after the learner stopped (glass to glass, minus device)")
    await room.leave()
    out.write_bytes(wav(bytes(room.npc_audio)))  # noqa: ASYNC240 - once, after the scene
    log(f"NPC audio saved to {out}")
    return turns_out


async def night(api: Api, session_id: str, wait_s: int = 300) -> dict[str, Any] | None:
    started = time.monotonic()
    await api.post(f"/v1/sessions/{session_id}/end")
    while time.monotonic() - started < wait_s:
        day = await api.get(f"/v1/sessions/{session_id}")
        if day.get("notebook"):
            log(f"night notebook ready {time.monotonic() - started:.0f}s after the day ended")
            return dict(day["notebook"])
        await asyncio.sleep(5)
    log(f"no notebook after {wait_s}s")
    return None


async def clone_round_trip(api: Api, language: str, out_dir: Path) -> dict[str, Any]:
    me = await api.get("/v1/me")
    consents = dict(me["consents"])
    report: dict[str, Any] = {}
    await api.http.patch("/v1/me", json={"consents": {**consents, "voice_clone": True}})
    try:
        sample = say(CLONE_TEXT[language], language)
        log(f"clone sample: {len(sample) / 2 / RATE:.1f}s")
        started = time.monotonic()
        response = await api.http.post(
            "/v1/voice/clone", files={"sample": ("sample.wav", wav(sample), "audio/wav")}, data={"consent": "true"}
        )
        body = response.json() if response.is_success else {"detail": response.json().get("detail")}
        report["clone"] = {"status": response.status_code, **body, "s": round(time.monotonic() - started, 1)}
        log(f"clone: {report['clone']}")
        line = (await api.get("/v1/studio/items", language=language))[0]["line"]
        started = time.monotonic()
        reference = await api.http.get("/v1/studio/reference", params={"line": line, "language": language})
        report["golden"] = {
            "status": reference.status_code,
            "bytes": len(reference.content),
            "s": round(time.monotonic() - started, 1),
        }
        (out_dir / "golden_self.wav").write_bytes(reference.content)
        log(f"golden self for {line!r}: {report['golden']}")
        attempt = say(line, language)
        started = time.monotonic()
        scored = await api.http.post(
            "/v1/studio/shadow",
            files={"audio": ("attempt.wav", wav(attempt), "audio/wav")},
            data={"line": line, "language": language, "attempt": "1"},
        )
        report["shadow"] = {"status": scored.status_code, "s": round(time.monotonic() - started, 1), **scored.json()}
        log(f"shadow: {report['shadow']}")
    finally:
        deleted = await api.http.delete("/v1/voice/clone")
        after = await api.get("/v1/voice")
        report["delete"] = {"status": deleted.status_code, "after": after["status"]}
        log(f"clone deleted: {report['delete']}")
        await api.http.patch("/v1/me", json={"consents": consents})
    return report


async def main_async(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    api = Api(args.api)
    await api.sign_in()
    report: dict[str, Any] = {}
    if args.clone:
        report["clone"] = await clone_round_trip(api, CITY_LANGUAGE[args.city], out_dir)
    if args.turns:
        if args.scene:
            session_id, scene_id = None, args.scene
        else:
            session_id, scene_id = await ready_scene(api, args.city)
        report["turns"] = await play(api, scene_id, args.turns, out_dir / "npc_audio.wav")
        if session_id and not args.keep_day:
            report["notebook"] = await night(api, session_id)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:58000")
    parser.add_argument("--city", choices=["rivemont", "ashford"], default="rivemont")
    parser.add_argument("--scene", help="play this scene instead of the next day's first")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--clone", action="store_true")
    parser.add_argument("--keep-day", action="store_true", help="don't end the day afterwards")
    parser.add_argument("--out", default="e2e_out")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
