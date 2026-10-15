"""Live-mode scene simulation for ``contract_adherence`` / ``npc_band_control`` (real LLMs; costs money).

Each scene: real NPC actor through the real loop (loopback audio, scripted STT echoes the simulated learner's text),
an LLM-simulated learner, and an independent frontier judge on every delivered NPC line. Targets elicited are
measured from the real ``turn_assessment`` graph's evidence.
"""

from __future__ import annotations

import asyncio
import statistics
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from evals.framework import ROOT, Gate, SuiteResult
from evals.scenes import eval_briefs
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_SCALE
from lingard_contracts.live import LearnerTurnEnded, LiveSessionConfig, TurnPolicy
from lingard_contracts.scene import SceneContract
from lingard_curriculum.graph import InMemoryCurriculumGraph
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.agents.scene_compiler import SceneCompiler
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.graphs.turn_assessment import TurnState, build_turn_assessment
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.store import LearnerProfileView, MemoryStore, SceneRecord
from lingard_live.actor import NpcActor
from lingard_live.claims import LlmClaimChecker
from lingard_live.events import MemoryBus
from lingard_live.guard import ContractGuard, Verdict
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import build_scene
from lingard_live.settings import LiveSettings
from lingard_live.stt import ScriptedStt, Transcript
from lingard_live.transport import LoopbackTransport
from lingard_live.tts import ScriptedTts
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_world import load_city

LANGUAGE_NAMES = {"fr": "French", "en": "English"}
LEARNER_MS_PER_WORD = 450
"""About 2.2 words a second, an intermediate learner's pace; well above the gate's 180 ms/word plausibility floor."""


async def _assessment_deps(router: LLMRouter, prompts: PromptRegistry) -> tuple[GraphDeps, uuid.UUID]:
    curriculum = InMemoryCurriculumGraph()
    for language in ("fr", "en"):
        await seed_graph(curriculum, load_seed(ROOT / "content", language))
    store = MemoryStore()
    user_id = uuid.uuid4()
    store.profiles[user_id] = LearnerProfileView(user_id, "Sam", "ar", "tense", {}, {}, {"fr": 6, "en": 6})
    deps = GraphDeps(
        store=store,
        curriculum=curriculum,
        router=router,
        prompts=prompts,
        packs=PackLibrary(ROOT / "content"),
        pedagogy=load_pedagogy(),
        hints=MemoryHints(),
        content_root=ROOT / "content",
    )
    return deps, user_id


class Judgement(BaseModel):
    violation: bool
    material: bool = False
    language_ok: bool
    tutor_like: bool
    reason: str = ""


@dataclass
class SceneTally:
    lines: int = 0
    violations: int = 0
    material: int = 0
    leaks: int = 0
    tutor: int = 0
    required: int = 0
    elicited: int = 0
    sentences: int = 0
    claim_checked: int = 0
    replies: int = 0
    fillers: int = 0
    first_checked: int = 0
    """Replies whose first sentence needed the claim check: those are the ones where it can delay first audio."""
    claim_repaired: int = 0
    claim_withheld: int = 0
    claim_ms: list[float] = field(default_factory=list)
    samples: list[dict[str, object]] = field(default_factory=list)


async def compile_eval_scenes(deps: GraphDeps) -> list[SceneContract]:
    """Every eval template compiled by the real Scene Compiler, as production writes contracts."""
    rules = deps.pedagogy.scenes
    compiler = SceneCompiler(
        deps.router,
        deps.prompts,
        deps.curriculum,
        deps.content_root,
        facts_range=(rules.approved_facts_min, rules.approved_facts_max),
    )
    return list(await asyncio.gather(*(compiler.compile(brief) for brief in eval_briefs())))


async def run_live_scenes(scene_count: int, concurrency: int = 5) -> SuiteResult:
    content, prompts = ROOT / "content", PromptRegistry(ROOT / "prompts")
    settings = LiveSettings()
    router = LLMRouter(LLMConfig.load(ROOT / "config/llm.yaml"))
    languages = [load_language(content, "fr"), load_language(content, "en")]
    identifier = LanguageIdentifier(languages)
    deps, user_id = await _assessment_deps(router, prompts)
    graph: CompiledStateGraph[Any, Any, Any, Any] = build_turn_assessment(deps)
    compiled = await compile_eval_scenes(deps)
    bands = {brief.location_key: brief.learner_band for brief in eval_briefs()}
    claims = (
        LlmClaimChecker(
            router,
            prompts.get("claim_check"),
            deadline_s=settings.claim_check_deadline_s,
            context_lines=settings.claim_check_context_lines,
        )
        if settings.claim_check
        else None
    )
    guard = ContractGuard(identifier, claims=claims, claim_free_words=settings.claim_free_words)
    gate = asyncio.Semaphore(concurrency)

    async def one(index: int) -> SceneTally:
        contract = compiled[index % len(compiled)].model_copy(update={"scene_id": uuid.uuid4()})
        async with gate:
            band = bands[contract.location_key]
            return await _play(contract, band, deps, user_id, graph, guard, identifier, settings.filler_after_ms)

    tallies = await asyncio.gather(*(one(i) for i in range(scene_count)))
    total = SceneTally()
    for tally in tallies:
        for name in ("lines", "violations", "material", "leaks", "tutor", "required", "elicited", "sentences"):
            setattr(total, name, getattr(total, name) + getattr(tally, name))
        for name in ("claim_checked", "claim_repaired", "claim_withheld", "replies", "first_checked", "fillers"):
            setattr(total, name, getattr(total, name) + getattr(tally, name))
        total.claim_ms += tally.claim_ms
        total.samples += tally.samples
    facts = [len(c.approved_facts) for c in compiled]
    return SuiteResult(
        suite="contract_adherence",
        mode="live",
        metrics={
            "scenes": scene_count,
            "npc_lines": total.lines,
            "fact_violations_leaked": total.violations,
            "material_fact_violations": total.material,
            "language_leaks": total.leaks,
            "tutor_like_rate": round(total.tutor / max(total.lines, 1), 4),
            "targets_elicited_rate": round(total.elicited / max(total.required, 1), 4),
            "approved_facts_median": statistics.median(facts),
            "npc_sentences": total.sentences,
            "claim_checked_rate": round(total.claim_checked / max(total.sentences, 1), 4),
            "first_sentence_checked_rate": round(total.first_checked / max(total.replies, 1), 4),
            "filler_rate": round(total.fillers / max(total.replies, 1), 4),
            "claim_repaired": total.claim_repaired,
            "claim_withheld": total.claim_withheld,
            "claim_ms_p50": round(statistics.median(total.claim_ms)) if total.claim_ms else 0,
            "claim_ms_p95": round(statistics.quantiles(total.claim_ms, n=20)[18]) if len(total.claim_ms) > 1 else 0,
        },
        gates=[
            Gate("material_fact_violations", "==", 0),
            Gate("language_leaks", "==", 0),
            Gate("targets_elicited_rate", ">=", 0.85),
            Gate("tutor_like_rate", "<=", 0.10),
        ],
        notes=[
            f"claim check {'on' if claims else 'off'}; scenes compiled live ({min(facts)}–{max(facts)} approved facts)",
            "fact_violations_leaked counts colour too; the gate counts material violations (decision 0012)",
        ],
        samples=[{"compiled": [c.model_dump(mode="json") for c in compiled]}, *total.samples],
    )


async def _play(
    contract: SceneContract,
    band: int,
    deps: GraphDeps,
    user_id: uuid.UUID,
    graph: CompiledStateGraph[Any, Any, Any, Any],
    guard: ContractGuard,
    identifier: LanguageIdentifier,
    filler_after_ms: float | None,
) -> SceneTally:
    tally = SceneTally()
    hint_store = deps.hints
    assert isinstance(hint_store, MemoryHints)
    router, prompts, content = deps.router, deps.prompts, deps.content_root
    learner_prompt, judge_prompt = prompts.get("sim_learner"), prompts.get("fact_judge")
    runtime = build_scene(contract, content, learner_name="Sam")
    city = load_city(content, contract.city)
    npc = city.npc(contract.cast[0].npc_key)
    stt = ScriptedStt()
    session = await LoopbackTransport().open(
        LiveSessionConfig(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            scene_id=contract.scene_id,
            room="eval",
            locale=CITY_LOCALE[contract.city],
            policy=TurnPolicy(eot_ms=900),
        )
    )
    await deps.store.save_scene(SceneRecord(contract.scene_id, user_id, uuid.uuid4(), contract))
    bus = MemoryBus()
    loop = LiveLoop(
        session=session,
        state=runtime.state,
        identity=SceneIdentity(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), band),
        actor=NpcActor(router, prompts.get("npc_actor")),
        guard=guard,
        guard_ctx=runtime.guard_ctx,
        language=runtime.language,
        identifier=identifier,
        stt=stt,
        tts=ScriptedTts(),
        publisher=bus,
        hints=hint_store,  # as in production: turn_assessment's steering hints reach the next NPC reply
        filler_after_ms=filler_after_ms,
    )
    history: list[BaseMessage] = []
    assessed = hints = 0
    opening = await loop.opening()
    npc_lines = [opening.npc_text]
    learner_lines: list[str] = []
    system = learner_prompt.render(
        scale_name=LANGUAGE_SCALE[contract.language],
        band=band,
        language_name=LANGUAGE_NAMES[contract.language],
        npc_name=npc.name,
        goal=contract.learner_goal,
        weaknesses=", ".join(contract.targets.grammar),
    )
    for _ in range(min(contract.max_turns, 8)):
        history.append(HumanMessage(content=npc_lines[-1]))
        said = await router.text("mid", learner_prompt, router.messages("mid", system, "", history)[:-1] + history[-1:])
        history.append(AIMessage(content=said))
        learner_lines.append(said)
        stt.queue.append(Transcript(said, 0.95, "sim"))
        speech_ms = max(len(said.split()) * LEARNER_MS_PER_WORD, 1000)  # the gate rejects implausibly fast speech
        await loop.handle_turn(
            LearnerTurnEnded(
                audio=b"\x00\x00" * 16 * speech_ms,
                speech_start_ms=0,
                speech_end_ms=speech_ms,
                eot_decided_ms=speech_ms + 900,
            )
        )
        npc_lines.append(loop.outcomes[-1].npc_text)
        # Production assesses each turn as it is published (lingard_graphs.worker); here it runs before the next
        # learner line, so a hint is ready one reply sooner than it might be live.
        for event in bus.events[assessed:]:
            if event.speaker == "learner":
                result = await graph.ainvoke(TurnState(event=event.model_copy(update={"user_id": user_id})))
                hints += bool(result.get("hint"))
        assessed = len(bus.events)
    for outcome in loop.outcomes:
        if outcome.guard_results:
            tally.replies += 1
            tally.first_checked += outcome.guard_results[0].claim_ms is not None
            tally.fillers += outcome.timing.filler
        for result in outcome.guard_results:
            tally.sentences += 1
            if result.claim_ms is not None:
                tally.claim_checked += 1
                tally.claim_ms.append(result.claim_ms)
            if {"unsupported_claim", "claim_check_timeout"} & set(result.reasons):
                if result.verdict is Verdict.REWRITE:
                    tally.claim_repaired += 1
                else:
                    tally.claim_withheld += 1
                tally.samples.append(
                    {"scene": str(contract.scene_id), "guard": result.verdict.value, "to": result.text}
                )
    grounding = runtime.guard_ctx.grounding  # what the actor and the claim checker are given, nothing more
    for line in npc_lines:
        if not line:
            continue
        verdict = await router.structured(
            "frontier",
            judge_prompt,
            Judgement,
            [
                HumanMessage(
                    content=judge_prompt.render(
                        facts="\n".join(grounding),
                        learner_lines=" | ".join(learner_lines),
                        line=line,
                        language_name=LANGUAGE_NAMES[contract.language],
                    )
                )
            ],
        )
        tally.lines += 1
        tally.violations += verdict.violation
        tally.material += verdict.violation and verdict.material
        tally.leaks += not verdict.language_ok
        tally.tutor += verdict.tutor_like
        # Every judged line is kept (clean ones too), so a Guard change can be scored offline against this run.
        tally.samples.append(
            {
                "scene": str(contract.scene_id),
                "line": line,
                "violation": verdict.violation,
                "material": verdict.material,
                "judge": verdict.reason,
                "heard": learner_lines,
            }
        )
    evidence = [e for a in await deps.store.assessments_for_scene(contract.scene_id) for e in a.target_evidence]
    for spec in contract.evidence_required:
        tally.required += 1
        uses = sum(1 for e in evidence if e.node_key == spec.target)
        tally.elicited += uses >= spec.min_uses
        tally.samples.append(
            {"scene": str(contract.scene_id), "npc": npc.key, "target": spec.target, "uses": uses, "hints": hints}
        )
    return tally
