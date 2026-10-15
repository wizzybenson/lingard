import copy
from typing import Any

import pytest
from pydantic import ValidationError

from lingard_contracts.scene import SceneContract, npc_band_for, validate_contract


def spec_example() -> dict[str, Any]:
    """SPEC §9 example, completed with the fields the example omits."""
    return {
        "city": "rivemont",
        "location_key": "rivemont.vieux_port.apartment_3b",
        "cast": [{"npc_key": "landlord_martin", "role": "landlord", "mood": "defensive", "voice_id": "fr_m_40s_a"}],
        "learner_goal": "Récupérer votre dépôt de garantie",
        "targets": {
            "functions": ["fr.func.complain_politely", "fr.func.negotiate"],
            "grammar": ["fr.grammar.conditionnel_present", "fr.grammar.si_imparfait"],
            "lexset": ["fr.lex.housing.deposit_repairs"],
            "pron": ["fr.pron.nasal_vowels"],
        },
        "elicitation": [
            {"target": "fr.grammar.si_imparfait", "tactic": "Landlord asks what the tenant would do if he refused"},
            {"target": "fr.func.negotiate", "tactic": "Landlord offers half; waits for a counter-offer"},
            {"target": "fr.func.complain_politely", "tactic": "Landlord blames the tenant for the crack"},
            {"target": "fr.grammar.conditionnel_present", "tactic": "Landlord asks what would be fair"},
            {"target": "fr.lex.housing.deposit_repairs", "tactic": "Landlord lists repair costs item by item"},
        ],
        "approved_facts": ["Deposit was 900 dollars", "Wall has a small crack", "Lease ended 1 October"],
        "npc_language_band": 7,
        "accent_variety": ["fr-FR-standard"],
        "correction_style": {"default": "recast", "on_intelligibility_failure": "clarify"},
        "success_conditions": ["Learner proposes a counter-offer", "Learner references the lease"],
        "evidence_required": [{"target": "fr.grammar.si_imparfait", "min_uses": 1}],
        "max_turns": 24,
        "exits": [{"key": "walk_out", "trigger": "learner leaves", "consequence": "deposit dispute unresolved"}],
        "intensity": "tense",
        "pack_alignment": ["tef_canada.eo.section_b"],
    }


def test_spec_example_is_valid() -> None:
    contract = SceneContract.model_validate(spec_example())
    assert validate_contract(contract, learner_band=6) == []
    assert contract.success_conditions[0].description == "Learner proposes a counter-offer"


def codes(data: dict[str, Any], **kwargs: Any) -> set[str]:
    contract = SceneContract.model_validate(data)
    return {i.code for i in validate_contract(contract, **{"learner_band": 6, **kwargs})}


def test_missing_tactic_detected() -> None:
    data = spec_example()
    data["elicitation"] = data["elicitation"][:2]
    assert "missing_tactic" in codes(data)


def test_band_must_be_within_one() -> None:
    assert "band_out_of_range" in codes(spec_example(), learner_band=4)


def test_language_leak_in_targets() -> None:
    data = spec_example()
    data["targets"]["grammar"].append("en.grammar.present_perfect")
    data["elicitation"].append({"target": "en.grammar.present_perfect", "tactic": "asks about experiences"})
    assert "target_language" in codes(data)


def test_intensity_cap() -> None:
    assert "intensity_over_cap" in codes(spec_example(), intensity_cap="calm")


def test_evidence_without_target() -> None:
    data = spec_example()
    data["evidence_required"].append({"target": "fr.grammar.subjonctif_present", "min_uses": 1})
    assert "evidence_not_target" in codes(data)


def test_unknown_node() -> None:
    assert "unknown_target" in codes(spec_example(), known_nodes={"fr.func.negotiate"})


def test_location_and_accent_must_match_city() -> None:
    data = spec_example()
    data["location_key"] = "ashford.high_street.cafe"
    data["accent_variety"] = ["en-GB-standard"]
    assert {"location_city", "accent_language"} <= codes(data)


def test_bad_node_key_rejected_by_schema() -> None:
    data = copy.deepcopy(spec_example())
    data["targets"]["grammar"] = ["Grammar Si"]
    with pytest.raises(ValidationError):
        SceneContract.model_validate(data)


def test_npc_band_cap() -> None:
    assert npc_band_for(6) == 7
    assert npc_band_for(10) == 10
    assert npc_band_for(12) == 10


def test_fact_count_is_checked_against_the_configured_range() -> None:
    data = spec_example()
    assert "thin_facts" in codes(data, facts_range=(10, 18))
    assert "thin_facts" not in codes(data), "no range given: not checked"
    data["approved_facts"] = [f"Fact {i}" for i in range(20)]
    assert "too_many_facts" in codes(data, facts_range=(10, 18))
    data["approved_facts"] = data["approved_facts"][:12]
    assert not {"thin_facts", "too_many_facts"} & codes(data, facts_range=(10, 18))
