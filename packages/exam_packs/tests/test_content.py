"""The authored bank against the official blueprints: every part fillable, every question type present, every
answer reachable under its own rules."""

from pathlib import Path

import pytest

from lingard_contracts.common import PackId, Skill
from lingard_curriculum.packs import PackLibrary
from lingard_exam_packs.items import ItemBank
from lingard_exam_packs.serving import normalise, words

ROOT = Path(__file__).resolve().parents[3] / "content"
BANK = ItemBank.load(ROOT)
PACKS = PackLibrary(ROOT)


@pytest.mark.parametrize("pack_id", ["ielts_gt", "tef_canada"])
def test_every_part_can_be_filled_with_every_question_type(pack_id: PackId) -> None:
    for section in PACKS.pack(pack_id).ordered_sections():
        for part in section.part_list():
            if part.items is None:
                continue
            items = [i for group in BANK.sets(pack_id, section.id).values() for i in group if i.part == part.id]
            assert len(items) >= part.items, f"{part.id}: {len(items)} questions for {part.items}"
            missing = set(part.task_types) - {i.task_type for i in items}
            assert not missing, f"{part.id} has no {missing}"


def test_answers_obey_their_own_rules() -> None:
    for item in BANK.select("ielts_gt", Skill.READING) + BANK.select("ielts_gt", Skill.LISTENING):
        for answer in item.accepted:
            assert item.word_limit is None or words(answer) <= item.word_limit, f"{item.id}: {answer!r}"
        if item.response == "text" and item.skill.value == "reading":
            assert any(normalise(a) in normalise(item.stimulus) for a in item.accepted), f"{item.id} not in the text"


def test_sets_share_one_text_and_part() -> None:
    packs: tuple[PackId, ...] = ("ielts_gt", "tef_canada")
    for pack_id in packs:
        for section in PACKS.pack(pack_id).ordered_sections():
            for group in BANK.sets(pack_id, section.id).values():
                assert len({i.stimulus for i in group}) == 1 and len({i.part for i in group}) == 1, group[0].set_id


def test_true_false_not_given_keeps_its_order() -> None:
    tfng = [i for i in BANK.select("ielts_gt", Skill.READING) if i.task_type == "true_false_not_given"]
    assert tfng and all(i.options == ["TRUE", "FALSE", "NOT GIVEN"] and not i.shuffle for i in tfng)
