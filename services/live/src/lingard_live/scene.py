"""Assemble everything one scene needs on the live plane from its contract and city content."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from lingard_contracts.scene import SceneContract
from lingard_live.actor import ActorState
from lingard_live.guard import GuardContext
from lingard_live.languages import LanguageConfig, load_language
from lingard_live.settings import REPO_ROOT
from lingard_llm import Prompt, PromptRegistry
from lingard_world import load_city


@cache
def _default_grounding() -> Prompt:
    return PromptRegistry(REPO_ROOT / "prompts").get("npc_grounding")


@dataclass(frozen=True)
class SceneRuntime:
    state: ActorState
    guard_ctx: GuardContext
    language: LanguageConfig


def build_scene(
    contract: SceneContract,
    content_root: Path,
    *,
    learner_name: str,
    relationship: str | None = None,
    scene_vocabulary: list[str] | None = None,
    grounding_prompt: Prompt | None = None,
) -> SceneRuntime:
    """``scene_vocabulary``: lexset items of the scene's targets, so on-topic words are never flagged as over-band.
    ``grounding_prompt`` (default ``prompts/npc_grounding``) states who and where the NPC is for the claim checker."""
    city = load_city(content_root, contract.city)
    cast = contract.cast[0]
    persona = city.npc(cast.npc_key)
    location = city.location(contract.location_key)
    language = load_language(content_root, contract.language)
    names = [
        learner_name,
        city.city.name,
        location.name,
        *(city.npc(c.npc_key).name for c in contract.cast),
        *(d.name for d in city.city.districts),
    ]
    state = ActorState(
        contract=contract,
        persona=persona,
        cast=cast,
        location=location,
        city_name=city.city.name,
        learner_name=learner_name,
        relationship=relationship or "You have not met before.",
    )
    visible = [f"{h.label}: {h.text}" for h in location.hotspots if h.text]
    identity = (grounding_prompt or _default_grounding()).render(
        npc_name=persona.name,
        npc_role=persona.role,
        backstory=persona.backstory,
        location_name=location.name,
        city_name=city.city.name,
        location_description=location.description,
        learner_goal=contract.learner_goal,
        learner_name=learner_name,
    )
    grounding = [*contract.approved_facts, *persona.world_facts, *visible, *identity.splitlines()]
    guard_ctx = GuardContext.build(
        contract,
        language,
        world_facts=[*persona.world_facts, location.description, *visible],
        names=names,
        scene_vocabulary=[*(scene_vocabulary or []), *language.backchannels, *language.clarify],
        grounding=grounding,
    )
    return SceneRuntime(state=state, guard_ctx=guard_ctx, language=language)
