"""Audits the model recordings the Accent Studio plays: each drill text's model (what a learner without a clone hears
and imitates) is sent back through scoring as if a learner had said it. A model judged wrong on its own trained sound
would teach the mistake, so every one that isn't judged good (or left to the ear by design) is reported.

Drill progress the audit makes is cleared afterwards. Paid only for model renders the API hasn't cached yet.

    uv run python -m tools.voicebench.model_audit --language fr
"""

from __future__ import annotations

import argparse
import asyncio
import io
import wave

from dotenv import load_dotenv

from tools.voicebench.studio_robot import ROOT, Api, Report, reset


def pcm_of(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return bytes(w.readframes(w.getnframes()))


async def audit(api: Api, language: str, key: str, report: Report) -> int:
    view = await api.call("drill", "GET", f"/v1/studio/gym/{key}", params={"language": language})
    if view is None:
        return 0
    rungs = {2: view["words"], 3: view["pair_texts"], 4: view["phrases"], 5: [view["sentence"]]}
    checked = 0
    for stage, items in rungs.items():
        for item in items:
            text = item["text"]
            model = await api.call(
                f"model {text!r}", "GET", "/v1/studio/reference", params={"language": language, "line": text}
            )
            if model is None:
                continue
            result = await api.say(language, key, stage, text, pcm_of(model))
            checked += 1
            if result is None or result["good"] or result.get("by_ear"):
                continue
            heard = "; ".join(t["text"] for t in result["tips"])[:140] or f"score {result.get('intelligibility')}"
            report.hiccup(f"{key} rung {stage}: the model of {text!r} is judged wrong — {heard}")
    return checked


async def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:58000")
    parser.add_argument("--language", choices=["fr", "en"], default="fr")
    parser.add_argument("--drills", nargs="*", help="default: every drill")
    args = parser.parse_args()
    report = Report()
    api = Api(args.api, report)
    await api.sign_in()
    overview = await api.call("gym", "GET", "/v1/studio/gym", params={"language": args.language})
    keys = args.drills or [d["key"] for d in overview["drills"]]
    checked = 0
    try:
        for key in keys:
            checked += await audit(api, args.language, key, report)
    finally:
        await reset(api.user_id, args.language, keys)
    print(f"\n{checked} models checked, {len(report.hiccups)} judged wrong")
    for h in report.hiccups:
        print(f"  - {h}")


if __name__ == "__main__":
    asyncio.run(main())
