"""Mission debrief: which of a scene's objectives the learner met (with the words that show it) and how it ended.

The scene contract's success conditions are the mission's objectives and its exits are the possible endings; a judge
on the ``mid`` tier reads the transcript once the scene is over. Credit needs the learner's own words, so a scene the
character carried does not count as the learner's success.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lingard_contracts.events import TurnEvent
from lingard_contracts.scene import SceneContract
from lingard_llm import LLMRouter, PromptRegistry

Result = Literal["accomplished", "partial", "not_done"]


class ObjectiveCheck(BaseModel):
    index: int
    met: bool
    quote: str = ""


class Judgement(BaseModel):
    objectives: list[ObjectiveCheck]
    ending: str | None = None


class Debrief(BaseModel):
    result: Result
    objectives: list[tuple[str, bool]]
    """Each objective as the learner saw it, and whether they met it."""
    ending: str | None = None
    """What happened in the end, in the scene's own words (the reached exit's consequence)."""


def result_of(met: list[bool]) -> Result:
    if met and all(met):
        return "accomplished"
    return "partial" if any(met) else "not_done"


async def debrief(
    contract: SceneContract, turns: list[TurnEvent], npc_name: str, router: LLMRouter, prompts: PromptRegistry
) -> Debrief:
    objectives = [c.description for c in contract.success_conditions]
    learner = [t for t in turns if t.speaker == "learner" and t.transcript.strip()]
    if not learner:  # nothing said: nothing to judge, and nothing to pay for
        return Debrief(result="not_done", objectives=[(o, False) for o in objectives])
    prompt = prompts.get("mission_debrief")
    system, per_call = prompt.render_split(
        npc_name=npc_name,
        goal=contract.learner_goal,
        objectives="\n".join(f"{i}. {o}" for i, o in enumerate(objectives)),
        endings="\n".join(f"- {e.key}: {e.trigger} → {e.consequence}" for e in contract.exits),
        transcript="\n".join(f"{'Learner' if t.speaker == 'learner' else npc_name}: {t.transcript}" for t in turns),
    )
    judged = await router.structured("mid", prompt, Judgement, router.messages("mid", system, per_call))
    said = " ".join(t.transcript for t in learner).casefold()
    met = {c.index for c in judged.objectives if c.met and c.quote.strip() and _heard(c.quote, said)}
    checks = [(o, i in met) for i, o in enumerate(objectives)]
    ending = next((e.consequence for e in contract.exits if e.key == judged.ending), None)
    return Debrief(result=result_of([m for _, m in checks]), objectives=checks, ending=ending)


def _heard(quote: str, said: str) -> bool:
    """The quote must come from the learner's turns (a few words of it at least), never from the character's."""
    words = [w for w in quote.casefold().replace("…", " ").split() if len(w) > 2]
    return bool(words) and sum(w.strip(".,!?«»\"'") in said for w in words) >= max(1, len(words) // 2)
