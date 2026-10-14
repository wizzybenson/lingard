"""Scene contract (SPEC §9): the compiled spec an NPC cast must fulfil, plus its validator."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from lingard_contracts.common import CITY_LANGUAGE, Band, CityKey, NodeKey, Strict, node_language

Intensity = Literal["calm", "tense", "heated"]
INTENSITY_ORDER: dict[str, int] = {"calm": 0, "tense": 1, "heated": 2}
NPC_BAND_CAP = 10


class CastMember(Strict):
    npc_key: str
    role: str
    mood: str = "neutral"
    voice_id: str


class SceneTargets(Strict):
    functions: list[NodeKey] = Field(default_factory=list)
    grammar: list[NodeKey] = Field(default_factory=list)
    lexset: list[NodeKey] = Field(default_factory=list)
    pron: list[NodeKey] = Field(default_factory=list)

    def all(self) -> list[str]:
        return [*self.functions, *self.grammar, *self.lexset, *self.pron]

    def elicitable(self) -> list[str]:
        """Targets that need a tactic. Pronunciation is evidenced by any speech, so it needs none."""
        return [*self.functions, *self.grammar, *self.lexset]


class ElicitationTactic(Strict):
    target: NodeKey
    tactic: str = Field(min_length=8)


class CorrectionPolicy(Strict):
    default: Literal["recast", "clarify", "elicit"] = "recast"
    on_intelligibility_failure: Literal["recast", "clarify", "elicit"] = "clarify"


class Condition(Strict):
    description: str = Field(min_length=3)
    target: NodeKey | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value: Any) -> Any:
        return {"description": value} if isinstance(value, str) else value


class EvidenceSpec(Strict):
    target: NodeKey
    min_uses: int = Field(default=1, ge=1)


class Exit(Strict):
    key: str
    trigger: str
    consequence: str


class SceneContract(Strict):
    scene_id: UUID = Field(default_factory=uuid4)
    city: CityKey
    location_key: str
    cast: list[CastMember] = Field(min_length=1)
    learner_goal: str = Field(min_length=3)
    targets: SceneTargets
    elicitation: list[ElicitationTactic]
    approved_facts: list[str] = Field(min_length=1)
    npc_language_band: Band
    speech_rate: Literal["slow", "normal", "fast"] = "normal"
    accent_variety: list[str] = Field(min_length=1)
    correction_style: CorrectionPolicy = Field(default_factory=CorrectionPolicy)
    success_conditions: list[Condition] = Field(min_length=1)
    evidence_required: list[EvidenceSpec] = Field(default_factory=list)
    max_turns: int = Field(ge=4, le=80)
    exits: list[Exit] = Field(min_length=1)
    intensity: Intensity = "calm"
    pack_alignment: list[str] = Field(default_factory=list)

    @property
    def language(self) -> str:
        return CITY_LANGUAGE[self.city]


class ContractIssue(Strict):
    code: str
    message: str


def validate_contract(
    contract: SceneContract,
    *,
    learner_band: int,
    intensity_cap: Intensity = "heated",
    known_nodes: set[str] | None = None,
) -> list[ContractIssue]:
    """Semantic checks beyond the schema. An empty list means the contract may be played.

    ``known_nodes`` (reviewed curriculum keys) is optional so the check also runs offline in tests.
    """
    issues: list[ContractIssue] = []

    def issue(code: str, message: str) -> None:
        issues.append(ContractIssue(code=code, message=message))

    targets = contract.targets.all()
    if not targets:
        issue("no_targets", "contract has no pedagogical targets")

    language = contract.language
    for key in targets:
        if node_language(key) != language:
            issue("target_language", f"target {key} is not in the city language {language}")
        if known_nodes is not None and key not in known_nodes:
            issue("unknown_target", f"target {key} is not a reviewed curriculum node")

    tactic_targets = {t.target for t in contract.elicitation}
    for key in contract.targets.elicitable():
        if key not in tactic_targets:
            issue("missing_tactic", f"target {key} has no elicitation tactic")
    for tactic in contract.elicitation:
        if tactic.target not in targets:
            issue("orphan_tactic", f"tactic for {tactic.target} which is not a target")

    for evidence in contract.evidence_required:
        if evidence.target not in targets:
            issue("evidence_not_target", f"evidence required for {evidence.target} which is not a target")
        elif evidence.target in contract.targets.elicitable() and evidence.target not in tactic_targets:
            issue("evidence_no_path", f"evidence for {evidence.target} has no elicitation path")
        if evidence.min_uses * 2 > contract.max_turns:
            issue("evidence_unreachable", f"{evidence.min_uses} uses of {evidence.target} won't fit in max_turns")

    if abs(contract.npc_language_band - learner_band) > 1:
        issue("band_out_of_range", f"NPC band {contract.npc_language_band} not within ±1 of learner {learner_band}")
    if contract.npc_language_band > NPC_BAND_CAP:
        issue("band_over_cap", f"NPC band above cap {NPC_BAND_CAP}")

    if INTENSITY_ORDER[contract.intensity] > INTENSITY_ORDER[intensity_cap]:
        issue("intensity_over_cap", f"intensity {contract.intensity} exceeds learner cap {intensity_cap}")

    if not contract.location_key.startswith(f"{contract.city}."):
        issue("location_city", f"location {contract.location_key} is not in {contract.city}")

    expected_accent = f"{language}-"
    if any(not a.startswith(expected_accent) for a in contract.accent_variety):
        issue("accent_language", "accent variety does not match city language")

    if len({c.npc_key for c in contract.cast}) != len(contract.cast):
        issue("duplicate_cast", "an NPC appears twice in the cast")

    return issues


def npc_band_for(learner_band: int) -> int:
    """SPEC §9: NPC speaks one band above the learner, capped."""
    return min(learner_band + 1, NPC_BAND_CAP)
