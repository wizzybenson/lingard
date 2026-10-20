import json
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from lingard_contracts.common import Skill
from lingard_curriculum.packs import PackLibrary
from lingard_exam_packs.adaptive import estimate, next_item, should_stop
from lingard_exam_packs.generator import ItemGenerator
from lingard_exam_packs.items import Item, ItemBank, band_to_logit
from lingard_exam_packs.serving import check, is_correct, serve, serve_set, served_answer, words
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel

ROOT = Path(__file__).resolve().parents[3]


def test_seed_bank_loads_both_packs_and_spans_bands() -> None:
    bank = ItemBank.load(ROOT / "content")
    for pack in ("ielts_gt", "tef_canada"):
        for skill in (Skill.READING, Skill.LISTENING):
            items = bank.select(pack, skill)
            assert len(items) >= 12
            assert {int(i.band) for i in items} >= {4, 5, 6, 7, 8, 9, 10}


def test_item_validation() -> None:
    with pytest.raises(ValueError):
        Item(
            id="x",
            pack="ielts_gt",
            language="en",
            skill=Skill.READING,
            section="reading",
            task_type="t",
            band=5,
            stimulus="s",
            question="q?",
            options=["a", "a", "b"],
            answer=0,
        )


def test_shuffled_serving_maps_answers_back() -> None:
    item = ItemBank.load(ROOT / "content").get("fr-ce-001")
    served = serve(item, "learner-1")
    assert isinstance(item.answer, int)
    correct_text = item.options[item.answer]
    assert is_correct(item, "learner-1", served.options.index(correct_text))
    assert not is_correct(item, "learner-1", (served.options.index(correct_text) + 1) % len(served.options))
    assert served_answer(item, "learner-1") == served.options.index(correct_text)
    assert not is_correct(item, "learner-1", -1)
    positions = {serve(item, f"learner-{i}").options.index(correct_text) for i in range(30)}
    assert len(positions) > 1, "answer position varies by learner"
    assert serve(ItemBank.load(ROOT / "content").get("fr-co-001"), "l").text is None, "listening scripts never sent"


@pytest.mark.parametrize("true_band", [4.5, 7.0, 9.5])
def test_adaptive_staircase_recovers_simulated_ability(true_band: float) -> None:
    import random

    rng = random.Random(3)
    bank = [
        Item(
            id=f"i{b}-{k}",
            pack="tef_canada",
            language="fr",
            skill=Skill.READING,
            section="ce",
            task_type="t",
            band=b,
            stimulus=f"text {b} {k}",
            question="q?",
            options=["a", "b", "c", "d"],
            answer=0,
        )
        for b in [x / 2 for x in range(6, 25)]
        for k in range(4)
    ]
    theta_true = band_to_logit(true_band)
    responses: list[tuple[float, bool]] = []
    seen: set[str] = set()
    current = estimate([])
    while not should_stop(current, len(responses), se_threshold=0.45, max_items=25):
        item = next_item([i for i in bank if i.id not in seen], current)
        assert item is not None
        seen.add(item.id)
        p = 1 / (1 + 2.718281828 ** (-(theta_true - item.difficulty)))
        responses.append((item.difficulty, rng.random() < p))
        current = estimate(responses)
    assert abs(current.band - true_band) <= 1.5
    assert len(responses) <= 25


async def test_generator_validates_and_drops_bad_items() -> None:
    answer = {
        "items": [
            {
                "stimulus": "Avis : la piscine ferme à 20 h ce soir.",
                "question": "Quand ferme la piscine ?",
                "options": ["À 18 h", "À 20 h", "À 22 h", "Demain"],
                "answer": 1,
            },
            {
                "stimulus": "Texte valide ici pour le test.",
                "question": "Doublon ?",
                "options": ["x", "x", "y", "z"],
                "answer": 0,
            },
        ]
    }
    model = ScriptedChatModel(queue=[json.dumps(answer)])

    def factory(spec: ModelSpec) -> BaseChatModel:
        return model

    router = LLMRouter(
        LLMConfig.model_validate(
            {"tiers": {"mid": {"retries": 0, "models": [{"provider": "scripted", "model": "s"}]}}}
        ),
        factory=factory,
    )
    pack = PackLibrary(ROOT / "content").pack("tef_canada")
    items = await ItemGenerator(router, PromptRegistry(ROOT / "prompts")).generate(pack, Skill.READING, 5, 2)
    assert len(items) == 1 and items[0].source == "generated" and items[0].section == "comprehension_ecrite"


def _set_item(n: int, **fields: object) -> Item:
    base: dict[str, object] = {
        "id": f"s-q{n}",
        "pack": "ielts_gt",
        "language": "en",
        "skill": "listening",
        "section": "listening",
        "part": "part1",
        "task_type": "form_completion",
        "band": 5,
        "stimulus": "Agent: Can I take your name? Caller: It's Sarah Pike, P-I-K-E. The rent is 450 pounds.",
        "set_id": "s",
        "question": "Surname:",
    }
    return Item.model_validate({**base, **fields})


def test_text_answers_follow_the_ielts_rules() -> None:
    item = _set_item(1, response="text", accepted=["Pike"], word_limit=2)
    assert check(item, "x", " pike. ") and check(item, "x", "PIKE")
    assert not check(item, "x", "Pyke"), "spelling counts"
    rent = _set_item(2, response="text", accepted=["450 pounds", "£450"], word_limit=1)
    assert check(rent, "x", "£450") and check(rent, "x", "450 pounds"), "a number is not a word"
    assert not check(rent, "x", "about 450 pounds"), "over the word limit loses the mark"
    assert words("check-in desk") == 2 and words("12 March") == 1


def test_multi_and_fixed_order_items() -> None:
    multi = _set_item(3, response="multi", options=["a", "b", "c", "d", "e"], answer=[1, 3])
    served = serve(multi, "learner")
    picks = [served.options.index("b"), served.options.index("d")]
    assert served.picks == 2 and check(multi, "learner", picks) and check(multi, "learner", picks[::-1])
    assert not check(multi, "learner", picks[:1]) and not check(multi, "learner", "b")
    tfng = _set_item(4, options=["TRUE", "FALSE", "NOT GIVEN"], answer=2, shuffle=False)
    assert serve(tfng, "anyone").options == ["TRUE", "FALSE", "NOT GIVEN"] and check(tfng, "anyone", 2)
    assert not check(tfng, "anyone", True), "a boolean is not an option index"


def test_a_set_is_served_once_without_its_script_or_answers() -> None:
    items = [_set_item(1, response="text", accepted=["Pike"], word_limit=2), _set_item(2, options=["a", "b"], answer=0)]
    served = serve_set(items, "learner", audio_ref="tts:s-q1")
    assert served.text is None and served.audio_ref == "tts:s-q1" and len(served.questions) == 2
    dumped = served.model_dump_json()
    assert "Pike" not in dumped and "accepted" not in dumped and "answer" not in dumped


def test_invalid_shapes_are_refused() -> None:
    with pytest.raises(ValidationError):
        _set_item(1, response="text", accepted=[])
    with pytest.raises(ValidationError):
        _set_item(1, response="multi", options=["a", "b", "c"], answer=[1])
    with pytest.raises(ValidationError):
        _set_item(1, options=["a", "b"], answer=[0, 1])
