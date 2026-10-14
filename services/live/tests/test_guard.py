import time

import pytest

from lingard_live.guard import ContractGuard, GuardContext, Verdict


@pytest.mark.parametrize(
    "sentence",
    [
        "Bonjour Ernest, entrez donc.",
        "Le dépôt était de 900 dollars, c'est vrai.",
        "Cette fissure, je la vois bien.",
        "Monsieur, le bail a pris fin le 1er octobre.",
        "Je possède trois appartements ici, vous savez.",
        "Mm.",
    ],
)
async def test_on_contract_sentences_pass(guard: ContractGuard, guard_ctx: GuardContext, sentence: str) -> None:
    result = await guard.check(sentence, guard_ctx)
    assert result.verdict is Verdict.PASS, result.reasons


@pytest.mark.parametrize(
    ("sentence", "reason"),
    [
        ("Je vous rends 450 dollars, pas plus.", "off_contract_number"),
        ("J'ai repeint le mur en mai dernier.", "off_contract_date"),
        ("Mon avocat, Maître Dubois, s'en occupera.", "off_contract_name"),
        ("Sorry, I think you should pay for the wall.", "wrong_language"),
        ("Attention, on dit « si j'avais », pas « si j'aurais ».", "tutor"),
        ("En tant qu'intelligence artificielle, je ne peux pas.", "character_break"),
    ],
)
async def test_violations_are_blocked(
    guard: ContractGuard, guard_ctx: GuardContext, sentence: str, reason: str
) -> None:
    result = await guard.check(sentence, guard_ctx)
    assert result.verdict is Verdict.BLOCK
    assert any(r.startswith(reason) for r in result.reasons), result.reasons


async def test_learner_mentioned_numbers_may_be_echoed(guard: ContractGuard, guard_ctx: GuardContext) -> None:
    sentence = "Vous proposez 600 dollars ? Hmm."
    assert (await guard.check(sentence, guard_ctx)).verdict is Verdict.BLOCK
    guard_ctx.admit_learner_text("Je propose 600 dollars.")
    assert (await guard.check(sentence, guard_ctx)).verdict is Verdict.PASS


class Simplifier:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer

    async def simplify(self, sentence: str, band: int, language: str) -> str | None:
        return self.answer


async def test_over_band_sentence_is_rewritten_or_blocked(guard: ContractGuard, guard_ctx: GuardContext) -> None:
    fancy = "Votre récrimination procède d'une acrimonie fallacieuse."
    blocked = await guard.check(fancy, guard_ctx)
    assert blocked.verdict is Verdict.BLOCK and blocked.reasons[0].startswith("over_band")

    rewriting = ContractGuard(guard._identifier, rewriter=Simplifier("Je trouve que votre plainte n'est pas juste."))
    rewritten = await rewriting.check(fancy, guard_ctx)
    assert rewritten.verdict is Verdict.REWRITE and rewritten.text.startswith("Je trouve")

    still_bad = ContractGuard(guard._identifier, rewriter=Simplifier("Je vous donne 300 dollars."))
    assert (await still_bad.check(fancy, guard_ctx)).verdict is Verdict.BLOCK


async def test_rule_path_is_well_under_50ms(guard: ContractGuard, guard_ctx: GuardContext) -> None:
    sentences = [
        "Écoutez, je comprends, mais la fissure n'était pas là avant votre arrivée dans l'appartement.",
        "Si vous voulez, on peut regarder l'état des lieux ensemble demain matin.",
    ] * 50
    await guard.check(sentences[0], guard_ctx)  # warm wordfreq caches
    started = time.perf_counter()
    for sentence in sentences:
        guard.check_rules(sentence, guard_ctx)
    per_sentence_ms = (time.perf_counter() - started) * 1000 / len(sentences)
    assert per_sentence_ms < 50
    assert per_sentence_ms < 5, f"rule path regressed: {per_sentence_ms:.2f} ms/sentence"
