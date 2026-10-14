"""Assemble everything one scene needs on the live plane from its contract and city content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lingard_contracts.scene import SceneContract
from lingard_live.actor import ActorState
from lingard_live.guard import GuardContext
from lingard_live.languages import LanguageConfig, load_language
from lingard_world import load_city


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
) -> SceneRuntime:
    """``scene_vocabulary``: lexset items of the scene's targets, so on-topic words are never flagged as over-band."""
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
    guard_ctx = GuardContext.build(
        contract,
        language,
        world_facts=[*persona.world_facts, location.description],
        names=names,
        scene_vocabulary=[*(scene_vocabulary or []), *language.backchannels, *language.clarify],
    )
    return SceneRuntime(state=state, guard_ctx=guard_ctx, language=language)
