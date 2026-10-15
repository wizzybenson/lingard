import time
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage

from lingard_live.claims import LlmClaimChecker, ScriptedClaimChecker, parse_answer
from lingard_live.guard import ClaimCheck, ContractGuard, GuardContext, Verdict
from lingard_live.languages import LanguageIdentifier
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel, message_text

ROOT = Path(__file__).resolve().parents[3]


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("OK", ClaimCheck(supported=True)),
        ("ok.\n", ClaimCheck(supported=True)),
        ("FIX: Je dois vérifier.", ClaimCheck(supported=False, repair="Je dois vérifier.")),
        ('FIX: "I\'d have to check."', ClaimCheck(supported=False, repair="I'd have to check.")),
        ("FIX: NONE", ClaimCheck(supported=False)),
        ("The sentence is fine", ClaimCheck(supported=False)),
        ("", ClaimCheck(supported=False)),
    ],
)
def test_claim_answers_parse(raw: str, expected: ClaimCheck) -> None:
    assert parse_answer(raw) == expected


def _identifier() -> LanguageIdentifier:
    from lingard_live.languages import load_language

    return LanguageIdentifier([load_language(ROOT / "content", "fr"), load_language(ROOT / "content", "en")])


async def test_claim_repair_must_pass_the_rules_too(guard_ctx: GuardContext) -> None:
    claims = ScriptedClaimChecker(
        {
            "Il faut signer ici.": ClaimCheck(supported=False, repair="Il faut signer avant le 3 mai."),
            "Le formulaire est gratuit.": ClaimCheck(supported=False, repair="Je ne sais pas, il faut vérifier."),
            "Le formulaire est bleu.": ClaimCheck(supported=False, repair="Ah, le"),
        }
    )
    guard = ContractGuard(_identifier(), claims=claims)
    blocked = await guard.check("Il faut signer ici.", guard_ctx)
    assert blocked.verdict is Verdict.BLOCK and blocked.reasons == ("unsupported_claim",)
    repaired = await guard.check("Le formulaire est gratuit.", guard_ctx)
    assert (repaired.verdict, repaired.text) == (Verdict.REWRITE, "Je ne sais pas, il faut vérifier.")
    fragment = await guard.check("Le formulaire est bleu.", guard_ctx)
    assert fragment.verdict is Verdict.BLOCK, "a truncated repair is never spoken"
    rules_first = await guard.check("Je vous rends 450 dollars.", guard_ctx)
    assert rules_first.verdict is Verdict.BLOCK and "Je vous rends 450 dollars." not in claims.checked


async def test_llm_claim_checker_grounds_on_the_scene_and_blocks_on_timeout(guard_ctx: GuardContext) -> None:
    model = ScriptedChatModel(queue=["FIX: Je ne sais pas.", "OK"])

    def factory(spec: ModelSpec) -> ScriptedChatModel:
        return model

    config = LLMConfig.model_validate(
        {"tiers": {"guard": {"retries": 0, "models": [{"provider": "scripted", "model": "g"}]}}}
    )
    checker = LlmClaimChecker(
        LLMRouter(config, factory=factory),
        PromptRegistry(ROOT / "prompts").get("claim_check"),
        deadline_s=2,
        context_lines=8,
    )
    guard_ctx.admit_learner_text("Je veux mon dépôt.")
    result = await checker.check("Le dépôt est rendu sous dix jours.", guard_ctx)
    assert result == ClaimCheck(supported=False, repair="Je ne sais pas.")
    system, user = (message_text(m) for m in model.calls[0])
    assert "Le dépôt était de 900 dollars" in system and "Martin Lefebvre" in system and "French" in system
    assert "Je veux mon dépôt." in user and user.endswith("Le dépôt est rendu sous dix jours.")

    def slow_answer(messages: list[BaseMessage]) -> str:
        time.sleep(0.2)
        return "OK"

    model.responder = slow_answer
    slow = LlmClaimChecker(
        LLMRouter(config, factory=factory),
        PromptRegistry(ROOT / "prompts").get("claim_check"),
        deadline_s=0.05,
        context_lines=8,
    )
    assert await slow.check("Mm.", guard_ctx) == ClaimCheck(supported=False, timed_out=True)


@pytest.mark.parametrize(
    ("sentence", "needs"),
    [
        ("D'accord.", False),
        ("Mm, la fissure ?", False),
        ("Le dépôt était de 900 dollars ?", False),
        ("Le formulaire est gratuit.", True),
        ("C'est le plombier qui décide.", True),
        ("Le dépôt, le mur, la fissure, le bail : je vois bien tout ça.", True),
    ],
)
def test_only_sentences_that_could_add_a_claim_are_checked(guard_ctx: GuardContext, sentence: str, needs: bool) -> None:
    assert guard_ctx.needs_claim_check(sentence, 6) is needs


def test_learner_and_npc_words_become_known(guard_ctx: GuardContext) -> None:
    assert guard_ctx.needs_claim_check("Le serrurier ?", 6)
    guard_ctx.admit_learner_text("J'ai appelé un serrurier.")
    assert not guard_ctx.needs_claim_check("Le serrurier ?", 6)
    guard_ctx.admit_npc_text("Il faut un formulaire.")
    assert not guard_ctx.needs_claim_check("Un formulaire ?", 6)
