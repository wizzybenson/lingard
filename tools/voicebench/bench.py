"""Run the real ``LiveLoop`` turn path with simulated provider latencies and report the latency budget metrics.

Half the turns use the speculative path (preparation starts at ``TurnPolicy.speculation_ms`` of silence), half the
plain path, so both numbers are visible. Provider latencies come from ``profiles.yaml`` (planning assumptions until
replaced by measurements).
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models import BaseChatModel

from lingard_contracts.live import LearnerTurnEnded, LiveSessionConfig, SpeculativeTurn, TurnPolicy
from lingard_live.actor import NpcActor
from lingard_live.events import MemoryBus
from lingard_live.guard import ContractGuard
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import build_scene
from lingard_live.stt import ScriptedStt, Transcript
from lingard_live.transport import LoopbackTransport
from lingard_live.tts import ScriptedTts
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel
from tools.voicebench.stats import bootstrap_ci, percentile

ROOT = Path(__file__).resolve().parents[2]
EOT_MS = 900
HESITATION_RATE = 0.35
"""Assumed share of turns with a mid-utterance pause between speculation_ms and eot_ms (replace with recorded data)."""
REPLIES = {
    "fr": [
        "D'accord, je vois. Et le mur, alors ?",
        "Hmm. Vous savez, ce n'est pas si simple.",
        "Bon. On peut en parler.",
    ],
    "en": ["Right, I see. And the wall, then?", "Hmm. It's not that simple, you know.", "Fine. We can talk about it."],
}
LEARNER = {"fr": "Je voudrais en parler, s'il vous plaît.", "en": "I'd like to talk about it, please."}


@dataclass
class BenchReport:
    first_audio_ms: list[float] = field(default_factory=list)
    """As heard by the learner: end-of-turn decision → first NPC audio, including the downlink hop."""
    no_speculation_ms: list[float] = field(default_factory=list)
    guard_ms: list[float] = field(default_factory=list)
    wasted_drafts: int = 0
    notes: list[str] = field(default_factory=list)

    def metrics(self) -> dict[str, float]:
        if not self.first_audio_ms:
            return {}
        ci = bootstrap_ci(self.first_audio_ms, 50) or (0.0, 0.0)
        return {
            "turns": len(self.first_audio_ms) + len(self.no_speculation_ms),
            "first_audio_p50_ms": round(percentile(self.first_audio_ms, 50)),
            "first_audio_p95_ms": round(percentile(self.first_audio_ms, 95)),
            "first_audio_p50_ci_low": round(ci[0]),
            "first_audio_p50_ci_high": round(ci[1]),
            "no_speculation_p50_ms": round(percentile(self.no_speculation_ms, 50)),
            "no_speculation_p95_ms": round(percentile(self.no_speculation_ms, 95)),
            "wasted_drafts_per_turn": round(self.wasted_drafts / len(self.first_audio_ms), 3),
            "guard_p99_ms": round(percentile(self.guard_ms, 99), 3),
        }


def _sampler(profile: dict[str, Any], rng: random.Random) -> Callable[[str], float]:
    def draw(stage: str) -> float:
        spec = profile[stage]
        return float(rng.lognormvariate(0, spec["sigma"]) * spec["median"])

    return draw


async def run_bench(*, mode: str, turns: int, profile_name: str = "assumed_cloud", seed: int = 7) -> BenchReport:
    report = BenchReport()
    if mode == "live":
        report.notes.append("live latency needs provider keys and a LiveKit room; see docs/gates/phase-1.md")
        return report
    from evals.scenes import eval_scenes

    profile = yaml.safe_load((Path(__file__).parent / "profiles.yaml").read_text())[profile_name]
    report.notes.append(f"provider latencies from profile '{profile_name}' ({profile['status']}, {profile['as_of']})")
    rng = random.Random(seed)  # noqa: S311
    draw = _sampler(profile, rng)
    content = ROOT / "content"
    identifier = LanguageIdentifier([load_language(content, "fr"), load_language(content, "en")])
    prompt = PromptRegistry(ROOT / "prompts").get("npc_actor")
    scenes = eval_scenes(6)
    for i in range(turns):
        contract, band, _ = scenes[i % len(scenes)]
        runtime = build_scene(contract, content, learner_name="Sam")
        model = ScriptedChatModel(
            responder=lambda m, lang=contract.language, k=i: REPLIES[lang][k % 3],
            first_token_delay_s=draw("llm_first_token_ms") / 1000,
            token_delay_s=draw("llm_token_ms") / 1000,
        )

        def factory(spec: ModelSpec, model: BaseChatModel = model) -> BaseChatModel:
            return model

        router = LLMRouter(
            LLMConfig.model_validate(
                {"tiers": {"fast": {"retries": 0, "models": [{"provider": "scripted", "model": "s"}]}}}
            ),
            factory=factory,
        )
        session = await LoopbackTransport().open(
            LiveSessionConfig(
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                scene_id=contract.scene_id,
                room="bench",
                locale="fr-FR",
                policy=TurnPolicy(eot_ms=EOT_MS),
            )
        )
        bus = MemoryBus()
        loop = LiveLoop(
            session=session,
            state=runtime.state,
            identity=SceneIdentity(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), band),
            actor=NpcActor(router, prompt),
            guard=ContractGuard(identifier),
            guard_ctx=runtime.guard_ctx,
            language=runtime.language,
            identifier=identifier,
            stt=ScriptedStt([Transcript(LEARNER[contract.language], 0.95, "sim")], delay_ms=int(draw("stt_ms"))),
            tts=ScriptedTts(first_chunk_delay_ms=int(draw("tts_first_chunk_ms"))),
            publisher=bus,
            hints=bus,
        )
        end = LearnerTurnEnded(
            audio=b"\x00\x00" * 40000, speech_start_ms=0, speech_end_ms=2500, eot_decided_ms=2500 + EOT_MS
        )
        downlink = draw("network_ms")
        if i % 2:
            speculation = SpeculativeTurn(
                audio=end.audio,
                speech_start_ms=0,
                speech_end_ms=2500,
                at_ms=2500 + TurnPolicy(eot_ms=EOT_MS).speculation_ms,
            )
            await loop.handle_speculative_turn(speculation, end)
            target = report.first_audio_ms
            report.wasted_drafts += rng.random() < HESITATION_RATE
        else:
            await loop.handle_turn(end)
            target = report.no_speculation_ms
        outcome = loop.outcomes[-1]
        if outcome.timing.first_audio_ms is not None:
            target.append(outcome.timing.first_audio_ms + downlink)
        report.guard_ms.extend(outcome.timing.guard_ms)
    return report
