"""Shared builders for live-plane tests."""

from pathlib import Path
from typing import Any

from lingard_contracts.scene import SceneContract

CONTENT = Path(__file__).resolve().parents[3] / "content"


def deposit_contract(**overrides: Any) -> SceneContract:
    data: dict[str, Any] = {
        "city": "rivemont",
        "location_key": "rivemont.vieux_port.apartment_3b",
        "cast": [{"npc_key": "landlord_martin", "role": "landlord", "mood": "defensive", "voice_id": "fr_m_58_martin"}],
        "learner_goal": "Récupérer votre dépôt de garantie",
        "targets": {
            "functions": ["fr.func.negotiate"],
            "grammar": ["fr.grammar.si_imparfait"],
            "lexset": ["fr.lex.housing.deposit_repairs"],
        },
        "elicitation": [
            {"target": "fr.grammar.si_imparfait", "tactic": "Ask what the tenant would do if he refused"},
            {"target": "fr.func.negotiate", "tactic": "Offer half the deposit; wait for a counter-offer"},
            {"target": "fr.lex.housing.deposit_repairs", "tactic": "List the repair costs item by item"},
        ],
        "approved_facts": [
            "Le dépôt était de 900 dollars",
            "Le mur a une petite fissure",
            "Le bail a pris fin le 1er octobre",
        ],
        "npc_language_band": 7,
        "accent_variety": ["fr-FR-standard"],
        "success_conditions": ["Learner proposes a counter-offer"],
        "evidence_required": [{"target": "fr.grammar.si_imparfait", "min_uses": 1}],
        "max_turns": 12,
        "exits": [{"key": "agreement", "trigger": "they agree on an amount", "consequence": "deposit partly returned"}],
        "intensity": "tense",
    }
    data.update(overrides)
    return SceneContract.model_validate(data)


DEPOSIT_VOCAB = ["dépôt de garantie", "état des lieux", "fissure", "fuite", "plombier", "remise en état", "usure"]


import pytest  # noqa: E402

from lingard_live.guard import ContractGuard, GuardContext  # noqa: E402
from lingard_live.languages import LanguageIdentifier, load_language  # noqa: E402
from lingard_live.scene import SceneRuntime, build_scene  # noqa: E402


@pytest.fixture
def runtime() -> SceneRuntime:
    return build_scene(deposit_contract(), CONTENT, learner_name="Ernest", scene_vocabulary=DEPOSIT_VOCAB)


@pytest.fixture
def guard() -> ContractGuard:
    return ContractGuard(LanguageIdentifier([load_language(CONTENT, "fr"), load_language(CONTENT, "en")]))


@pytest.fixture
def guard_ctx(runtime: SceneRuntime) -> GuardContext:
    return runtime.guard_ctx
