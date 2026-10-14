"""Live provider probe: ``python -m tools.voicebench.probe [--runs 5] [--write-profile]`` (needs provider keys in .env).

Times every configured provider on the real critical path of a turn, in both languages:
- text-to-speech: time to the first audio chunk of an NPC line;
- speech-to-text: transcribing that synthesised line (also a rough accuracy check against the script);
- fast LLM tier: time to the first token of the NPC actor prompt for an eval scene, and the per-token rate.

``--write-profile`` stores the medians of the preferred providers as the ``measured`` profile in profiles.yaml, which
the ``latency`` eval then uses instead of the planning assumptions. Network latency stays assumed (it depends on the
learner's connection, not the providers).
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import functools
import json
import math
import operator
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from lingard_live.actor import build_messages
from lingard_live.languages import load_language
from lingard_live.scene import build_scene
from lingard_live.settings import LiveSettings, stt_providers, tts_providers
from lingard_live.tts import VoiceSpec
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_llm.config import PROVIDER_ENV, provider_configured

ROOT = Path(__file__).resolve().parents[2]
PROFILES = Path(__file__).parent / "profiles.yaml"
LINES = {
    "fr": "Bonjour ! Le loyer est payable le premier du mois, et le dépôt est de neuf cents dollars.",
    "en": "Hello! The rent is due on the first of the month, and the deposit is nine hundred pounds.",
}
LEARNER = {"fr": "Bonjour, je viens pour l'appartement.", "en": "Hi, I'm here about the flat."}


def _stats(samples: list[float]) -> dict[str, float]:
    logs = [math.log(max(s, 1.0)) for s in samples]
    return {
        "median": round(statistics.median(samples), 1),
        "p95": round(sorted(samples)[min(len(samples) - 1, int(0.95 * len(samples)))], 1),
        "sigma": round(statistics.pstdev(logs), 3) if len(logs) > 1 else 0.3,
    }


async def probe(runs: int) -> dict[str, Any]:
    settings = LiveSettings()
    out: dict[str, Any] = {"tts": {}, "stt": {}, "stt_similarity": {}, "llm_first_token": {}, "llm_token": {}}
    audio: dict[str, bytes] = {}
    for name, tts in tts_providers(settings).items():
        times = []
        for i in range(runs):
            language = ("fr", "en")[i % 2]
            narrator = load_language(settings.content_root, language).narrator_voice
            started, first, pcm = time.perf_counter(), None, b""
            async for chunk in tts.stream(LINES[language], VoiceSpec(voice_id=narrator, language=language)):
                first = first or time.perf_counter()
                pcm += chunk.pcm
            times.append(((first or time.perf_counter()) - started) * 1000)
            audio.setdefault(language, pcm)
        out["tts"][name] = _stats(times)
    for name, stt in stt_providers(settings).items():
        times, scores = [], []
        for i in range(runs):
            language = ("fr", "en")[i % 2]
            if language not in audio:
                continue
            started = time.perf_counter()
            result = await stt.transcribe(audio[language], load_language(settings.content_root, language).stt_locale)
            times.append((time.perf_counter() - started) * 1000)
            scores.append(difflib.SequenceMatcher(None, result.text.lower(), LINES[language].lower()).ratio())
        if times:
            out["stt"][name] = _stats(times)
            out["stt_similarity"][name] = round(statistics.mean(scores), 3)
    from evals.scenes import eval_scenes  # evals is a sibling top-level package, imported where it is used

    config = LLMConfig.load(ROOT / "config" / "llm.yaml")
    prompt = PromptRegistry(ROOT / "prompts").get("npc_actor")
    scenes = eval_scenes(6)
    for provider in (p for p in PROVIDER_ENV if provider_configured(p)):
        router = LLMRouter(config, available=functools.partial(operator.eq, provider))
        first_times, token_times = [], []
        for i in range(runs):
            contract, _, _ = scenes[i % len(scenes)]
            runtime = build_scene(contract, ROOT / "content", learner_name="Sam")
            messages = build_messages(prompt, runtime.state, provider, LEARNER[contract.language], None)
            started, first, pieces = time.perf_counter(), None, 0
            async for _ in router.stream("fast", prompt, messages):
                first = first or time.perf_counter()
                pieces += 1
            end = time.perf_counter()
            if first is not None:
                first_times.append((first - started) * 1000)
                token_times.append((end - first) * 1000 / max(pieces - 1, 1))
        if first_times:
            out["llm_first_token"][provider] = _stats(first_times)
            out["llm_token"][provider] = _stats(token_times)
    return out


def measured_profile(result: dict[str, Any], assumed: dict[str, Any]) -> dict[str, Any]:
    """The preferred provider per stage (first in each result group, which keeps preference order)."""

    def first(group: str) -> dict[str, float] | None:
        return next(iter(result[group].values()), None)

    profile: dict[str, Any] = {"status": "measured", "as_of": date.today().isoformat(), "providers": {}}
    for stage, group in (
        ("stt_ms", "stt"),
        ("tts_first_chunk_ms", "tts"),
        ("llm_first_token_ms", "llm_first_token"),
        ("llm_token_ms", "llm_token"),
    ):
        stats = first(group)
        profile[stage] = {"median": stats["median"], "sigma": stats["sigma"]} if stats else assumed[stage]
        profile["providers"][stage] = next(iter(result[group]), "assumed")
    profile["network_ms"] = assumed["network_ms"]
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Time every configured STT, TTS and LLM provider.")
    parser.add_argument("--runs", type=int, default=6)
    parser.add_argument("--write-profile", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    result = asyncio.run(probe(args.runs))
    print(json.dumps(result, indent=2))
    out = ROOT / "evals" / "results" / "provider_probe.json"
    out.write_text(json.dumps({"as_of": date.today().isoformat(), **result}, indent=2) + "\n")
    if args.write_profile:
        profiles = yaml.safe_load(PROFILES.read_text())
        profiles["measured"] = measured_profile(result, profiles["assumed_cloud"])
        PROFILES.write_text(yaml.safe_dump(profiles, sort_keys=False, allow_unicode=True))
        print("wrote the 'measured' profile to tools/voicebench/profiles.yaml", file=sys.stderr)


if __name__ == "__main__":
    main()
