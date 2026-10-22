"""What could I say? Three lines a stuck learner could say next in a live scene, at their level, with their meaning.

The learner asks for them from the scene screen; the conversation so far is what the app captioned. The lines move
the mission's objectives forward and never show the scene's hidden targets (SPEC §9).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_SCALE
from lingard_contracts.scene import SceneContract
from lingard_llm import LLMRouter, PromptRegistry

MAX_LINES = 8
"""The latest lines of the conversation the helper reads: what was just asked matters, the start rarely does."""


class Line(BaseModel):
    speaker: str
    """``learner`` or ``npc``."""
    text: str = Field(max_length=600)


class Suggestion(BaseModel):
    text: str
    meaning: str
    step: int | None = None


class Suggestions(BaseModel):
    suggestions: list[Suggestion]


async def say_next(
    contract: SceneContract,
    lines: list[Line],
    *,
    npc_name: str,
    npc_role: str,
    band: int,
    explain_language: str,
    router: LLMRouter,
    prompts: PromptRegistry,
) -> list[Suggestion]:
    objectives = [c.description for c in contract.success_conditions]
    prompt = prompts.get("say_next")
    recent = lines[-MAX_LINES:]
    system, per_call = prompt.render_split(
        npc_name=npc_name,
        npc_role=npc_role,
        language_name=LANGUAGE_NAME[contract.language],
        scale_name=LANGUAGE_SCALE[contract.language],
        band=band,
        goal=contract.learner_goal,
        objectives="\n".join(f"{i}. {o}" for i, o in enumerate(objectives)),
        explain_language=explain_language,
        transcript="\n".join(f"{'Learner' if line.speaker == 'learner' else npc_name}: {line.text}" for line in recent)
        or "(nothing yet: the learner speaks first)",
    )
    answer = await router.structured("fast", prompt, Suggestions, router.messages("fast", system, per_call))
    steps = range(len(objectives))
    return [
        s.model_copy(update={"step": s.step if s.step in steps else None})
        for s in answer.suggestions[:3]
        if s.text.strip()
    ]
