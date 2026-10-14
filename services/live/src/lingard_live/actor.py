"""NPC Actor (SPEC §6.3, §10): builds the cached-prefix prompt and streams the NPC's reply."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_SCALE
from lingard_contracts.scene import CastMember, SceneContract
from lingard_contracts.world import Location, NpcPersona
from lingard_llm import LLMRouter, Prompt
from lingard_llm.router import cached_system

MAX_HISTORY_TURNS = 24


@dataclass
class DialogueTurn:
    speaker: str  # "learner" | npc_key
    text: str


@dataclass
class ActorState:
    """Working memory for one scene (SPEC §14): contract, rolling dialogue, pending steering hint."""

    contract: SceneContract
    persona: NpcPersona
    cast: CastMember
    location: Location
    city_name: str
    learner_name: str
    relationship: str = "You have not met before."
    dialogue: list[DialogueTurn] = field(default_factory=list)
    pending_hint: str | None = None
    interrupted: bool = False


def render_system(prompt: Prompt, state: ActorState) -> str:
    contract, persona = state.contract, state.persona
    language = contract.language
    facts = "\n".join(f"- {f}" for f in [*contract.approved_facts, *persona.world_facts])
    tactics = "\n".join(f"- {t.tactic}" for t in contract.elicitation) or "- Just be yourself."
    exits = "; ".join(f"{e.trigger} → {e.consequence}" for e in contract.exits)
    style = contract.correction_style
    return prompt.render(
        npc_name=persona.name,
        npc_role=persona.role,
        city_name=state.city_name,
        learner_name=state.learner_name,
        npc_age=persona.age,
        personality=persona.personality,
        backstory=persona.backstory,
        speech_style=persona.speech_style,
        mood=state.cast.mood,
        intensity=contract.intensity,
        language_name=LANGUAGE_NAME[language],
        npc_band=contract.npc_language_band,
        scale_name=LANGUAGE_SCALE[language],
        speech_rate=contract.speech_rate,
        accent=", ".join(contract.accent_variety),
        correction_style=f"default {style.default}; if unintelligible, {style.on_intelligibility_failure}",
        facts=facts,
        location_name=state.location.name,
        location_description=state.location.description,
        learner_goal=contract.learner_goal,
        tactics=tactics,
        exits=exits,
        relationship=state.relationship,
    )


def build_messages(
    prompt: Prompt, state: ActorState, provider: str, pending_learner: str | None = None, hint: str | None = None
) -> list[BaseMessage]:
    """Pure: ``pending_learner`` and ``hint`` are added to the request without touching the scene state."""
    notes = []
    if state.interrupted:
        notes.append("The newcomer interrupted you mid-sentence; respond to what they said.")
    if hint:
        notes.append(f"Director's note (act on it, never mention it): {hint}")
    system = cached_system(render_system(prompt, state), provider, " ".join(notes) or None)
    messages: list[BaseMessage] = [system]
    dialogue = [*state.dialogue, DialogueTurn("learner", pending_learner)] if pending_learner else state.dialogue
    for turn in dialogue[-MAX_HISTORY_TURNS:]:
        if turn.speaker == "learner":
            messages.append(HumanMessage(content=turn.text))
        else:
            messages.append(AIMessage(content=turn.text))
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content="(The newcomer is waiting for you to speak.)"))
    return messages


class NpcActor:
    def __init__(self, router: LLMRouter, prompt: Prompt) -> None:
        self._router = router
        self._prompt = prompt

    @property
    def prompt(self) -> Prompt:
        return self._prompt

    def reply(
        self,
        state: ActorState,
        trace_id: str | None = None,
        *,
        pending_learner: str | None = None,
        hint: str | None = None,
    ) -> AsyncIterator[str]:
        messages = build_messages(
            self._prompt, state, self._router.primary_provider("fast"), pending_learner, hint or state.pending_hint
        )
        return self._router.stream("fast", self._prompt, messages, trace_id=trace_id)
