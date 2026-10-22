from typing import Any

from langchain_core.messages import BaseMessage

from lingard_graphs.agents.learning_coach import (
    REASON_CHARS,
    CoachBrief,
    RuleCandidate,
    SlipCandidate,
    SoundCandidate,
    coach,
)
from lingard_graphs.deps import GraphDeps

from .conftest import Script

BRIEF = CoachBrief(
    language="fr",
    band=6,
    exam_name="TEF Canada",
    explain_language="English",
    skills={"speaking": "behind", "listening": "close"},
    learned=["Le présent"],
    slips=[
        SlipCandidate(node_key="fr.grammar.passe_compose_etre", title="Passé composé avec être", said="j'ai allé",
                      better="je suis allé", times=2),
    ],
    rules=[
        RuleCandidate(node_key="fr.grammar.imparfait", title="Imparfait", kind="grammar", band=6, in_use=0.2),
        RuleCandidate(node_key="fr.grammar.futur_proche", title="Futur proche", kind="grammar", band=5, in_use=0.7),
    ],
    sounds=[SoundCandidate(drill="fr.pron.u_vs_ou", title="/y/ et /u/", score=41.0)],
)  # fmt: skip


async def test_the_coach_reads_the_learners_progress_and_chooses_among_candidates(
    deps: GraphDeps, script: Script
) -> None:
    def answer(messages: list[BaseMessage]) -> dict[str, Any]:
        brief = str(messages[-2].content)
        assert "Said “j'ai allé”, better “je suis allé” (2 scenes)" in brief, "the learner's own words reach the coach"
        assert "fr.grammar.imparfait: Imparfait (grammar, level 6, 0.20)" in brief, "and how surely they use each rule"
        assert "speaking behind" in brief and "/y/ et /u/ (41)" in brief
        return {
            "fix": "fr.grammar.passe_compose_etre",
            "learn": "fr.grammar.subjonctif",  # not a candidate: dropped
            "sound": "fr.pron.u_vs_ou",
            "why": {
                "fix": "You said “j'ai allé” in two scenes: aller takes être.",
                "learn": "The subjonctif unlocks everything.",
                "sounds": "x" * 400,
                "story": "Today at the bank you'll tell what happened.",
            },
        }

    script.handlers["You are the learning coach"] = answer
    plan = await coach(BRIEF, router=deps.router, prompts=deps.prompts)
    assert plan.fix == "fr.grammar.passe_compose_etre" and plan.sound == "fr.pron.u_vs_ou"
    assert plan.learn is None and plan.why.learn is None, "a rule outside the candidates and its reason are dropped"
    assert plan.why.fix and "être" in plan.why.fix
    assert plan.why.sounds and len(plan.why.sounds) == REASON_CHARS, "a reason is cut to a card's sentence"
    assert plan.why.warmup is None
