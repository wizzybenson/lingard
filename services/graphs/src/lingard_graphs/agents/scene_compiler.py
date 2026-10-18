"""Scene Compiler (SPEC §10): ``SceneBrief`` → validated ``SceneContract``.

Builds on Simupatient's validated-case pattern (immutable version + readiness check before use); the scenario
generator is new: the LLM writes the creative parts and code fixes everything structural.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_NAME, LANGUAGE_PACK, LANGUAGE_SCALE
from lingard_contracts.planning import SceneBrief
from lingard_contracts.scene import (
    CastMember,
    Condition,
    ContractIssue,
    CorrectionPolicy,
    ElicitationTactic,
    EvidenceSpec,
    Exit,
    SceneContract,
    SceneTargets,
    npc_band_for,
    validate_contract,
)
from lingard_curriculum.graph import CurriculumGraph
from lingard_curriculum.models import CurriculumNode
from lingard_llm import LLMRouter, PromptRegistry
from lingard_world import load_city

EXAM_NAMES = {"tef_canada": "TEF Canada", "ielts_gt": "IELTS General Training"}
KIND_FIELD = {"function": "functions", "grammar": "grammar", "lexset": "lexset", "pron": "pron"}


class SceneDraft(BaseModel):
    learner_goal: str
    elicitation: list[ElicitationTactic]
    approved_facts: list[str] = Field(min_length=1)
    success_conditions: list[str] = Field(min_length=1, max_length=4)
    evidence_required: list[EvidenceSpec] = Field(default_factory=list)
    exits: list[Exit] = Field(min_length=1, max_length=4)
    max_turns: int = Field(ge=8, le=40)
    mood: str = "neutral"


class CompileError(RuntimeError):
    def __init__(self, issues: list[ContractIssue]) -> None:
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))
        self.issues = issues


def describe_target(node: CurriculumNode) -> str:
    detail = ""
    lesson = node.payload.get("lesson")
    if isinstance(lesson, dict) and lesson.get("rule"):
        detail = f" — {lesson['rule']}"
    elif node.payload.get("exponents"):
        detail = f" — e.g. {'; '.join(node.payload['exponents'][:3])}"
    elif node.payload.get("items"):
        detail = f" — words: {', '.join(map(str, node.payload['items'][:8]))}"
    return f"- {node.key} ({node.kind}): {node.title}{detail}"


def learner_address(content_root: Path, language: str) -> str:
    """How scene goals address the learner, from ``content/languages/<language>.yaml`` (decision 0015)."""
    data = yaml.safe_load((content_root / "languages" / f"{language}.yaml").read_text())
    return str(data["learner_address"])


class SceneCompiler:
    def __init__(
        self,
        router: LLMRouter,
        prompts: PromptRegistry,
        curriculum: CurriculumGraph,
        content_root: Path,
        *,
        facts_range: tuple[int, int],
        max_attempts: int = 3,
    ) -> None:
        """``facts_range``: (min, max) approved facts per scene, from the ``scenes`` pedagogy config."""
        self._router = router
        self._prompt = prompts.get("scene_compiler")
        self._curriculum = curriculum
        self._content = content_root
        self._attempts = max_attempts
        self._facts_range = facts_range

    async def _nodes(self, keys: list[str]) -> list[CurriculumNode]:
        nodes = []
        for key in keys:
            node = await self._curriculum.get(key)
            if node is None or not node.reviewed:
                raise CompileError([ContractIssue(code="unknown_target", message=f"{key} is not a reviewed node")])
            nodes.append(node)
        return nodes

    async def compile(self, brief: SceneBrief, *, trace_id: str | None = None) -> SceneContract:
        language = CITY_LANGUAGE[brief.city]
        city = load_city(self._content, brief.city)
        npc = city.npc(brief.npc_keys[0])
        location = city.location(brief.location_key)
        nodes = await self._nodes(brief.targets)
        targets = SceneTargets()
        for node in nodes:
            getattr(targets, KIND_FIELD[node.kind]).append(node.key)
        system = self._prompt.render(
            city_name=city.city.name,
            exam=EXAM_NAMES[LANGUAGE_PACK[language]],
            location_name=location.name,
            location_description=location.description,
            npc_name=npc.name,
            npc_role=npc.role,
            personality=npc.personality,
            speech_style=npc.speech_style,
            world_facts="; ".join(npc.world_facts),
            visible="; ".join(f"{h.label}: {h.text}" for h in location.hotspots if h.text) or "nothing written",
            facts_min=self._facts_range[0],
            facts_max=self._facts_range[1],
            learner_band=brief.learner_band,
            scale_name=LANGUAGE_SCALE[language],
            intensity=brief.intensity,
            story_beat=brief.story_beat,
            pack_alignment=", ".join(brief.pack_alignment) or "general",
            targets="\n".join(describe_target(n) for n in nodes),
            language_name=LANGUAGE_NAME[language],
            learner_address=learner_address(self._content, language),
        )
        messages = self._router.messages("compile", system, "Design the scene now.")
        issues: list[ContractIssue] = []
        for _ in range(self._attempts):
            draft = await self._router.structured("compile", self._prompt, SceneDraft, messages, trace_id=trace_id)
            contract = SceneContract(
                city=brief.city,
                location_key=brief.location_key,
                cast=[CastMember(npc_key=npc.key, role=npc.role, mood=draft.mood, voice_id=npc.voice_id)],
                learner_goal=draft.learner_goal,
                targets=targets,
                elicitation=draft.elicitation,
                approved_facts=draft.approved_facts,
                npc_language_band=npc_band_for(brief.learner_band),
                speech_rate="slow" if brief.learner_band <= 4 else "normal",
                accent_variety=[npc.accent],
                correction_style=CorrectionPolicy(),
                success_conditions=[Condition(description=c) for c in draft.success_conditions],
                evidence_required=draft.evidence_required,
                max_turns=draft.max_turns,
                exits=draft.exits,
                intensity=brief.intensity,
                pack_alignment=brief.pack_alignment,
            )
            issues = validate_contract(
                contract,
                learner_band=brief.learner_band,
                intensity_cap=brief.intensity,
                known_nodes={n.key for n in nodes},
                facts_range=self._facts_range,
            )
            if not issues:
                return contract
            feedback = "Fix these problems and return the whole JSON again:\n" + "\n".join(
                f"- {i.code}: {i.message}" for i in issues
            )
            messages = [*messages, HumanMessage(content=feedback)]
        raise CompileError(issues)
