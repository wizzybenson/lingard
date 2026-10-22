import uuid
from typing import Any

from langchain_core.messages import BaseMessage

from lingard_contracts.events import TurnEvent
from lingard_contracts.scene import SceneContract
from lingard_graphs.agents.debrief import debrief, result_of
from lingard_graphs.deps import GraphDeps

from .conftest import Script

CONTRACT = SceneContract.model_validate(
    {
        "city": "rivemont",
        "location_key": "rivemont.vieux_port.apartment_3b",
        "cast": [{"npc_key": "landlord_martin", "role": "landlord", "voice_id": "fr_m_58_martin"}],
        "learner_goal": "Récupérer votre dépôt de garantie",
        "targets": {"grammar": ["fr.grammar.si_imparfait"]},
        "elicitation": [{"target": "fr.grammar.si_imparfait", "tactic": "Ask what the tenant would do if refused"}],
        "approved_facts": ["Le dépôt était de 900 dollars"],
        "npc_language_band": 7,
        "accent_variety": ["fr-FR-standard"],
        "success_conditions": ["Proposez un montant à rembourser.", "Mentionnez l'état des lieux."],
        "max_turns": 12,
        "exits": [
            {"key": "deal", "trigger": "agree on an amount", "consequence": "Martin vous rend 700 $."},
            {"key": "walk_out", "trigger": "leave", "consequence": "Vous partez sans votre dépôt."},
        ],
    }
)


def turn(speaker: str, text: str, index: int) -> TurnEvent:
    return TurnEvent(
        trace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        scene_id=CONTRACT.scene_id,
        turn_index=index,
        speaker=speaker,
        language="fr-FR",
        transcript=text,
    )


TURNS = [
    turn("npc", "Je garde 300 $ pour la fissure, l'état des lieux le montre.", 0),
    turn("learner", "Je propose que vous me rendiez 700 dollars.", 1),
    turn("npc", "D'accord, 700 $.", 2),
]


async def test_credit_needs_the_learners_own_words(deps: GraphDeps, script: Script) -> None:
    def judge(_: list[BaseMessage]) -> dict[str, Any]:
        return {
            "objectives": [
                {"index": 0, "met": True, "quote": "vous me rendiez 700 dollars"},
                {"index": 1, "met": True, "quote": "l'état des lieux le montre"},  # the landlord said this
            ],
            "ending": "deal",
        }

    script.handlers["You judge how a learner did"] = judge
    result = await debrief(CONTRACT, TURNS, "Martin", deps.router, deps.prompts)
    assert result.objectives == [("Proposez un montant à rembourser.", True), ("Mentionnez l'état des lieux.", False)]
    assert result.result == "partial" and result.ending == "Martin vous rend 700 $."


async def test_silence_is_not_judged_or_paid(deps: GraphDeps, script: Script) -> None:
    result = await debrief(CONTRACT, TURNS[:1], "Martin", deps.router, deps.prompts)
    assert result.result == "not_done" and not script.calls


def test_results() -> None:
    assert result_of([True, True]) == "accomplished"
    assert result_of([True, False]) == "partial"
    assert result_of([False]) == result_of([]) == "not_done"


async def test_say_next_offers_three_lines_tied_to_the_missions_steps(deps: GraphDeps, script: Script) -> None:
    from lingard_graphs.agents.say_next import Line, say_next

    def helper(messages: list[BaseMessage]) -> dict[str, Any]:
        assert "Martin: Je garde 300 $" in str(messages[-2].content)
        return {
            "suggestions": [
                {"text": "Je propose 700 dollars.", "meaning": "I suggest 700 dollars.", "step": 0},
                {"text": "On peut regarder l'état des lieux ?", "meaning": "Can we look at the report?", "step": 1},
                {"text": "Je comprends.", "meaning": "I understand.", "step": 9},
                {"text": "Merci.", "meaning": "Thanks.", "step": None},
            ]
        }

    script.handlers["You help a language learner who is stuck"] = helper
    lines = [Line(speaker="npc", text="Je garde 300 $ pour la fissure.")]
    out = await say_next(
        CONTRACT,
        lines,
        npc_name="Martin",
        npc_role="landlord",
        band=5,
        explain_language="English",
        router=deps.router,
        prompts=deps.prompts,
    )
    assert [s.text for s in out] == ["Je propose 700 dollars.", "On peut regarder l'état des lieux ?", "Je comprends."]
    assert [s.step for s in out] == [0, 1, None], "a step the mission doesn't have is dropped"
