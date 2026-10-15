"""Live-mode scene simulation for ``contract_adherence`` / ``npc_band_control`` (real LLMs; costs money).

Each scene: real NPC actor through the real loop (loopback audio, scripted STT echoes the simulated learner's text),
an LLM-simulated learner, and an independent frontier judge on every delivered NPC line. Targets elicited are
measured from the real ``turn_assessment`` graph's evidence.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from evals.framework import ROOT, Gate, SuiteResult
from evals.scenes import eval_scenes
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_SCALE
from lingard_contracts.live import LearnerTurnEnded, LiveSessionConfig, TurnPolicy
from lingard_curriculum.graph import InMemoryCurriculumGraph
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.graphs.turn_assessment import TurnState, build_turn_assessment
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.store import LearnerProfileView, MemoryStore, SceneRecord
from lingard_live.actor import NpcActor
from lingard_live.events import MemoryBus
from lingard_live.guard import ContractGuard
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import build_scene
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
    language_ok: bool
    tutor_like: bool
    reason: str = ""


async def run_live_scenes(scene_count: int) -> SuiteResult:
    content, prompts = ROOT / "content", PromptRegistry(ROOT / "prompts")
    router = LLMRouter(LLMConfig.load(ROOT / "config/llm.yaml"))
    languages = [load_language(content, "fr"), load_language(content, "en")]
    identifier = LanguageIdentifier(languages)
    learner_prompt, judge_prompt = prompts.get("sim_learner"), prompts.get("fact_judge")
    deps, user_id = await _assessment_deps(router, prompts)
    graph: CompiledStateGraph[Any, Any, Any, Any] = build_turn_assessment(deps)
    hint_store = deps.hints
    assert isinstance(hint_store, MemoryHints)
    lines = violations = leaks = tutor = 0
    elicited = required = 0
    samples: list[dict[str, object]] = []
    for contract, band, _ in eval_scenes(scene_count):
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
            guard=ContractGuard(identifier),
            guard_ctx=runtime.guard_ctx,
            language=runtime.language,
            identifier=identifier,
            stt=stt,
            tts=ScriptedTts(),
            publisher=bus,
            hints=hint_store,  # as in production: turn_assessment's steering hints reach the next NPC reply
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
            said = await router.text(
                "mid", learner_prompt, router.messages("mid", system, "", history)[:-1] + history[-1:]
            )
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
        location = city.location(contract.location_key)
        # What the actor is given about itself and the place, as the Guard grounds it (lingard_live.scene).
        grounding = [
            *contract.approved_facts,
            *npc.world_facts,
            f"The character is {npc.name}, {npc.role}. Background: {npc.backstory}",
            f"What the other speaker wants here: {contract.learner_goal}",
            f"The place is {location.name}, in {runtime.state.city_name}: {location.description}",
            f"The other speaker is {runtime.state.learner_name}.",
        ]
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
            lines += 1
            violations += verdict.violation
            leaks += not verdict.language_ok
            tutor += verdict.tutor_like
            if verdict.violation or not verdict.language_ok or verdict.tutor_like:
                samples.append({"scene": str(contract.scene_id), "line": line, "judge": verdict.reason})
        evidence = [e for a in await deps.store.assessments_for_scene(contract.scene_id) for e in a.target_evidence]
        for spec in contract.evidence_required:
            required += 1
            uses = sum(1 for e in evidence if e.node_key == spec.target)
            elicited += uses >= spec.min_uses
            samples.append(
                {"scene": str(contract.scene_id), "npc": npc.key, "target": spec.target, "uses": uses, "hints": hints}
            )
    return SuiteResult(
        suite="contract_adherence",
        mode="live",
        metrics={
            "scenes": scene_count,
            "npc_lines": lines,
            "fact_violations_leaked": violations,
            "language_leaks": leaks,
            "tutor_like_rate": round(tutor / max(lines, 1), 4),
            "targets_elicited_rate": round(elicited / max(required, 1), 4),
        },
        gates=[
            Gate("fact_violations_leaked", "==", 0),
            Gate("language_leaks", "==", 0),
            Gate("targets_elicited_rate", ">=", 0.85),
            Gate("tutor_like_rate", "<=", 0.10),
        ],
        samples=samples,
    )
