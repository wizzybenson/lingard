"""A robot learner for the Accent Studio: climbs sound-gym drills through the running API with real recorded speech.

For each drill it starts from scratch (its progress is cleared for the test learner), learns the sounds, takes the
listening quiz, then says every spoken item with a native recording it did not hear as the model (another voice),
and at every spoken stage also says the classic mistake (the minimal-pair partner) to check the mistake is caught
with a tip that names it. It ends with a review. Any 4xx/5xx, a mistake that passes, a right take that fails twice, a
stage that doesn't climb, or a slow answer is reported as a hiccup.

Native takes come from the calibration cache (``tools/content_cli/calibrate.py`` renders them; run it first). Paid only
for model renders the API hasn't cached yet (a few ElevenLabs characters).

    uv run python -m tools.voicebench.studio_robot --language fr --drills fr.pron.u_vs_ou fr.gym.statement_question
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / ".cache" / "lingard" / "calibration"
LEARNER_VOICES = ("nova", "alloy", "onyx")
SLOW_S = 8.0


@dataclass
class Report:
    hiccups: list[str] = field(default_factory=list)
    timings: list[tuple[str, float]] = field(default_factory=list)

    def hiccup(self, text: str) -> None:
        self.hiccups.append(text)
        print(f"  ! {text}")


def wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(pcm)
    return out.getvalue()


async def melody_take(language: str, text: str, voice: str) -> bytes | None:
    """A take of a melody-drill text said the way the drill asks (a question rising, a statement falling), as a learner
    practising it would: the calibration takes were read without instructions, and British voices often fall on a
    yes/no question. Rendered by OpenAI and cached."""
    import yaml

    from lingard_live.audio import resample
    from lingard_pronunciation.gym import ending

    want = ending(text)
    if want is None:
        return None
    path = CACHE / language / f"melody-{voice}" / f"{hashlib.sha256(text.encode()).hexdigest()[:20]}.pcm"
    if path.exists():
        return path.read_bytes()
    gym = yaml.safe_load((ROOT / "content" / "pronunciation" / f"sounds_{language}.yaml").read_text())
    style = gym["melody_model"]["question" if want == "rise" else "statement"]
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "instructions": style, "response_format": "pcm"}
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        response = await client.post("https://api.openai.com/v1/audio/speech", json=body)
    response.raise_for_status()
    pcm = resample(response.content, 24_000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm)
    return pcm


def take(language: str, text: str, voice: str) -> bytes | None:
    """A native recording of ``text``; a pair ("a / b") is its two words with a pause between."""
    if " / " in text:
        parts = [take(language, t, voice) for t in text.split(" / ")]
        if any(p is None for p in parts):
            return None
        return parts[0] + b"\0\0" * 6400 + parts[1]  # type: ignore[operator]
    path = CACHE / language / voice / f"{hashlib.sha256(text.encode()).hexdigest()[:20]}.pcm"
    return path.read_bytes() if path.exists() else None


async def reset(user_id: uuid.UUID, language: str, keys: list[str]) -> None:
    """Clears these drills' progress for the test learner, so each run climbs from the bottom."""
    from lingard_api.settings import Settings
    from lingard_api.state import AppState
    from lingard_db.models import LearnerProfile

    state = AppState.build(Settings())
    try:
        async with state.sessions() as db:
            profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == user_id))).scalar_one()
            gym = dict(profile.settings.get("gym", {}))
            gym[language] = {k: v for k, v in gym.get(language, {}).items() if k not in keys}
            profile.settings = {**profile.settings, "gym": gym}
            await db.commit()
    finally:
        await state.close()


class Api:
    def __init__(self, base: str, report: Report) -> None:
        self.http = httpx.AsyncClient(base_url=base, timeout=120)
        self.report = report

    async def call(self, label: str, method: str, path: str, **kwargs: Any) -> Any:
        started = time.monotonic()
        response = await self.http.request(method, path, **kwargs)
        elapsed = time.monotonic() - started
        self.report.timings.append((label, elapsed))
        if elapsed > SLOW_S:
            self.report.hiccup(f"{label} took {elapsed:.1f}s")
        if response.status_code >= 400:
            self.report.hiccup(f"{label}: HTTP {response.status_code} {response.text[:200]}")
            return None
        return response.json() if "json" in response.headers.get("content-type", "") else response.content

    async def sign_in(self) -> None:
        body = {"display_name": os.environ["LINGARD_TEST_NAME"], "pin": os.environ["LINGARD_TEST_PIN"]}
        token = (await self.http.post("/v1/auth/sign-in", json=body)).json()["access_token"]
        self.http.headers["Authorization"] = f"Bearer {token}"
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        self.user_id = uuid.UUID(claims["sub"])

    async def say(self, language: str, drill: str, stage: int, text: str, pcm: bytes) -> dict[str, Any] | None:
        form = {"line": text, "language": language, "drill": drill, "stage": str(stage)}
        files = {"audio": ("take.wav", wav(pcm), "audio/wav")}
        result: dict[str, Any] | None = await self.call(
            f"say {text!r}", "POST", "/v1/studio/shadow", data=form, files=files
        )
        return result


def partner_of(view: dict[str, Any], text: str) -> str | None:
    """The minimal-pair partner of a word, when the drill has one."""
    for a, b in view["pairs"]:
        if text == a:
            return str(b)
        if text == b:
            return str(a)
    return None


async def climb(api: Api, language: str, key: str, report: Report) -> None:
    print(f"\n== {key}")
    view = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
    if view is None:
        return
    stages: list[int] = view["stages"]
    if view["stage"] != stages[0]:
        report.hiccup(f"{key}: a fresh drill starts on rung {view['stage']}, not {stages[0]}")
    if 0 in stages:
        if not all(g["how"]["steps"] and g["how"]["check"] for g in view["guides"]):
            report.hiccup(f"{key}: a sound has no steps or self-check")
        await api.call("learned", "POST", f"/v1/studio/gym/{key}/step", json={"language": language, "stage": 0})
    if 1 in stages:
        for word in {w for pair in view["pairs"] for w in pair}:
            if (
                await api.call(
                    f"model {word!r}", "GET", "/v1/studio/reference", params={"language": language, "line": word}
                )
                is None
            ):
                report.hiccup(f"{key}: no model recording for {word!r}")
        failed = await api.call(
            "quiz 4/8", "POST", f"/v1/studio/gym/{key}/step", json={"language": language, "stage": 1, "score": 0.5}
        )
        if failed and failed["passed"]:
            report.hiccup(f"{key}: half the listening quiz wrong still passed")
        await api.call(
            "quiz 7/8", "POST", f"/v1/studio/gym/{key}/step", json={"language": language, "stage": 1, "score": 0.875}
        )

    for _ in range(12):  # the spoken rungs, each until it climbs
        view = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
        if view is None or view["mastered"]:
            break
        stage = view["stage"]
        items = {2: view["words"], 3: view["pair_texts"], 4: view["phrases"], 5: [view["sentence"]]}[stage]
        print(f"  rung {stage}: {len(items)} items, {view['needed']} to say well")
        mistake_checked = False
        for item in items:
            text = item["text"]
            wrong_text = partner_of(view, text)
            if not mistake_checked and wrong_text and (wrong := take(language, wrong_text, LEARNER_VOICES[0])):
                result = await api.say(language, key, stage, text, wrong)
                mistake_checked = True
                if result and result.get("by_ear"):
                    print(f"    mistake {wrong_text!r} for {text!r}: compared by ear, as designed (not machine-judged)")
                elif result and result["good"]:
                    report.hiccup(f"{key}: saying {wrong_text!r} for {text!r} passed")
                elif result and not any(t.get("heard_as") for t in result["tips"]):
                    report.hiccup(f"{key}: the mistake {wrong_text!r} for {text!r} got no tip naming it")
                else:
                    print(
                        f"    mistake {wrong_text!r} for {text!r}: caught"
                        + (f" — {result['tips'][0]['text'][:70]}" if result and result["tips"] else "")
                    )
            good = False
            for voice in LEARNER_VOICES:
                pcm = (await melody_take(language, text, voice) if view["focus"] == "intonation" else None) or take(
                    language, text, voice
                )
                if pcm is None:
                    continue
                result = await api.say(language, key, stage, text, pcm)
                if result is None:
                    break
                if result["good"]:
                    good = True
                    break
            if not good:
                report.hiccup(f"{key}: no native take of {text!r} was judged good at rung {stage}")
            fresh = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
            if fresh is None or fresh["stage"] != stage or fresh["mastered"]:
                break
        after = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
        if after and after["stage"] == stage and not after["mastered"]:
            report.hiccup(f"{key}: rung {stage} did not climb after every item was said")
            break
    view = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
    if not view or not view["mastered"] or not view["due"]:
        report.hiccup(f"{key}: not mastered with a review date after the climb")
        return
    print(f"  climbed; first review {view['due'][:10]}")
    held = await api.call("review", "POST", f"/v1/studio/gym/{key}/review", json={"language": language, "held": True})
    if not held or held["reviews"] != 1:
        report.hiccup(f"{key}: a held review was not counted")
    slipped = await api.call(
        "review", "POST", f"/v1/studio/gym/{key}/review", json={"language": language, "held": False}
    )
    if not slipped or slipped["stage"] < 2:
        report.hiccup(f"{key}: a slipped review did not send the drill back to its words")


async def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:58000")
    parser.add_argument("--language", choices=["fr", "en"], default="fr")
    parser.add_argument("--drills", nargs="+", required=True)
    args = parser.parse_args()
    report = Report()
    api = Api(args.api, report)
    await api.sign_in()
    await reset(api.user_id, args.language, args.drills)
    await api.call("focus", "PATCH", "/v1/me", json={"focus_language": args.language})
    overview = await api.call("gym", "GET", "/v1/studio/gym", params={"language": args.language})
    if overview and not overview["workout"]:
        report.hiccup("the workout is empty")
    for key in args.drills:
        await climb(api, args.language, key, report)
    scored = [t for label, t in report.timings if label.startswith("say")]
    if scored:
        scored.sort()
        print(f"\nscoring: {len(scored)} takes, median {scored[len(scored) // 2]:.1f}s, slowest {scored[-1]:.1f}s")
    print(f"{len(report.hiccups)} hiccup(s)" + ("" if not report.hiccups else ":"))
    for h in report.hiccups:
        print(f"  - {h}")


if __name__ == "__main__":
    asyncio.run(main())
