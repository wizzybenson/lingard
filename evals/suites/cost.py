"""``cost`` (SPEC §25 Phase 5: ≤ 1 USD per active hour): projected cost of one active hour, per provider stack.

Offline it measures the real prompts: a synthetic learner plays three days through the real graphs (every planning
and assessment prompt), and the NPC actor's prompt is built for the eval scenes. Token counts use the scripted
models' estimate (4 characters per token). Scripted replies are shorter than real ones, so each prompt's output is
the larger of the measured size and the floor in ``config/cost_model.yaml``. Activity per hour, cache shares and
speech prices come from that file too; they are assumptions until live play measures them.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

import yaml

from evals.framework import ROOT, Gate, Mode, SuiteResult, suite
from evals.scenes import eval_scenes
from evals.synthetic_learners.harness import build_deps, live_days
from evals.synthetic_learners.learner import default_cohort
from lingard_contracts.common import LANGUAGE_NAME
from lingard_live.actor import build_messages
from lingard_live.scene import build_scene
from lingard_llm import LLMConfig, PromptRegistry
from lingard_llm.config import ModelSpec
from lingard_llm.testing import message_text
from lingard_llm.usage import cost_usd

DAYS = 3
DEFAULT_STACK = ("anthropic", "deepgram", "elevenlabs")
PER_TURN = ("utterance_assessor", "correction_check")
PER_SCENE = ("scene_compiler",)


async def _measured() -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Mean input/output tokens and call counts per prompt over a short synthetic run."""
    deps = await build_deps()
    await live_days(default_cohort()[0], DAYS, deps)
    calls: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for record in deps.router.sink.records:  # type: ignore[attr-defined]
        calls[record.prompt.split("@")[0]].append((record.input_tokens, record.output_tokens, record.tier))
    sizes = {
        name: {
            "input": sum(i for i, _, _ in rows) / len(rows),
            "output": sum(o for _, o, _ in rows) / len(rows),
            "tier": rows[0][2],
        }
        for name, rows in calls.items()
    }
    return sizes, {name: len(rows) for name, rows in calls.items()}


def _actor_input_tokens() -> float:
    prompt = PromptRegistry(ROOT / "prompts").get("npc_actor")
    sizes = []
    for contract, _, _ in eval_scenes(12):
        runtime = build_scene(contract, ROOT / "content", learner_name="Sam")
        messages = build_messages(prompt, runtime.state, "anthropic", "Bonjour, j'ai une question.", None)
        sizes.append(sum(len(message_text(m)) for m in messages) / 4)
    return sum(sizes) / len(sizes)


def _claim_input_tokens() -> float:
    """The claim check's grounding plus a few lines of dialogue and the sentence (decision 0012)."""
    prompt = PromptRegistry(ROOT / "prompts").get("claim_check")
    sizes = []
    for contract, _, _ in eval_scenes(12):
        ctx = build_scene(contract, ROOT / "content", learner_name="Sam").guard_ctx
        system = prompt.render(
            facts="\n".join(f"- {f}" for f in ctx.grounding), language_name=LANGUAGE_NAME[contract.language]
        )
        sizes.append(len(system) / 4)
    return sum(sizes) / len(sizes)


def _model(config: LLMConfig, tier: str, provider: str) -> ModelSpec:
    return next(m for m in config.tier(tier).models if m.provider == provider)  # type: ignore[arg-type]


def hourly_cost(
    sizes: dict[str, dict[str, Any]],
    counts: dict[str, int],
    actor_input: float,
    model: dict[str, Any],
    config: LLMConfig,
    stack: tuple[str, str, str],
    claim_input: float = 0,
) -> dict[str, float]:
    activity, speech = model["activity"], model["speech"]
    floors: dict[str, int] = model["output_floor_tokens"]
    cached: dict[str, float] = model["cached_share"]
    llm, stt, tts = stack
    scenes = activity["scenes_per_hour"]
    turns = scenes * activity["learner_turns_per_scene"]
    harness_scenes = max(counts.get("scene_compiler", 1), 1)
    harness_turns = max(counts.get("utterance_assessor", 1), 1)

    def per_hour(name: str) -> float:
        if name in PER_TURN:
            return float(counts[name] / harness_turns * turns)
        if name in PER_SCENE:
            return float(counts[name] / harness_scenes * scenes)
        return float(counts[name] / DAYS * activity["sessions_per_hour"])

    breakdown: dict[str, float] = defaultdict(float)
    for name, size in sizes.items():
        spec = _model(config, size["tier"], llm)
        tokens_in, tokens_out = size["input"], max(size["output"], floors.get(name, 0))
        cache = tokens_in * cached.get(name, 0)
        breakdown[f"llm_{size['tier']}"] += per_hour(name) * cost_usd(
            spec.price, int(tokens_in), int(tokens_out), int(cache)
        )
    actor_in = actor_input + activity["history_tokens_per_turn"] * activity["learner_turns_per_scene"] / 2
    actor = _model(config, "fast", llm)
    breakdown["llm_fast"] += turns * cost_usd(
        actor.price, int(actor_in), floors["npc_actor"], int(actor_in * activity["actor_cached_share"])
    )
    if claim_input:
        checker = _model(config, "guard", llm)
        claim_in = claim_input + activity["claim_context_tokens"]
        breakdown["llm_guard"] += (
            turns
            * activity["claim_checks_per_turn"]
            * cost_usd(
                checker.price, int(claim_in), floors["claim_check"], int(claim_input * cached.get("claim_check", 0))
            )
        )
    minutes = turns * activity["learner_speech_seconds_per_turn"] / 60
    breakdown["stt"] = minutes * speech["stt"][stt]["per_minute"]
    breakdown["tts"] = turns * activity["npc_chars_per_turn"] / 1000 * speech["tts"][tts]["per_1k_chars"]
    breakdown["total"] = sum(breakdown.values())
    return {k: round(v, 4) for k, v in breakdown.items()}


@suite("cost", watches=("config/llm.yaml", "config/cost_model.yaml", "prompts/"))
async def cost(mode: Mode) -> SuiteResult:
    model = yaml.safe_load((ROOT / "config" / "cost_model.yaml").read_text())
    config = LLMConfig.load(ROOT / "config" / "llm.yaml")
    sizes, counts = await _measured()
    actor_input = _actor_input_tokens()
    # Only providers with a model in every tier can run alone (e.g. OpenAI has no fast-tier model, decision 0009).
    providers = [
        p
        for p in ("anthropic", "openai", "google")
        if all(any(m.provider == p for m in t.models) for t in config.tiers.values())
    ]
    stacks = list(itertools.product(providers, model["speech"]["stt"], model["speech"]["tts"]))
    claim_input = _claim_input_tokens()
    results = {stack: hourly_cost(sizes, counts, actor_input, model, config, stack, claim_input) for stack in stacks}
    default = results[DEFAULT_STACK]
    cheapest = min(results, key=lambda s: results[s]["total"])
    metrics: dict[str, float] = {f"default_{k}": v for k, v in default.items()}
    metrics.update({f"llm_only_{p}": results[(p, "voicebox", "voicebox")]["total"] for p in providers})
    metrics["cheapest_total"] = results[cheapest]["total"]
    notes = [
        f"default stack {'+'.join(DEFAULT_STACK)}; cheapest {'+'.join(cheapest)}",
        f"activity assumptions as_of {model['activity']['as_of']} ({model['activity']['status']})",
        "per-call tokens: " + ", ".join(f"{n} {s['input']:.0f}→{s['output']:.0f}" for n, s in sorted(sizes.items())),
        f"actor prompt ≈ {actor_input:.0f} tokens before history; claim check ≈ {claim_input:.0f} before dialogue",
    ]
    samples = [{"stack": "+".join(s), **results[s]} for s in sorted(results, key=lambda s: results[s]["total"])]
    return SuiteResult("cost", mode, metrics, [Gate("default_total", "<=", 1.0)], notes=notes, samples=samples)
