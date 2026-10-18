"""Contract Guard (SPEC §10): every NPC sentence → pass / rewrite / block before any audio exists.

The rule path is pure Python on precomputed sets and is budgeted at ≤ 50 ms per sentence (tested well below).
Only an over-band sentence asks the optional ``Rewriter`` (fast tier) for a simpler paraphrase. Rules catch new
numbers, names and dates but not invented procedures, so a sentence that passes them goes to the optional
``ClaimChecker`` (the spec's "small classifier", decision 0012), which can repair it. The live loop runs that check
while earlier sentences play and the screened sentence's audio is prefetched (never played before it is confirmed),
so it stays off the rule budget.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from wordfreq import zipf_frequency

from lingard_contracts.scene import SceneContract
from lingard_live.languages import LanguageConfig, LanguageIdentifier, words
from lingard_live.sentences import is_complete

ZIPF_FLOOR_BY_BAND: list[tuple[int, float]] = [(4, 4.0), (5, 3.6), (6, 3.2), (7, 2.9), (8, 2.6), (9, 2.2)]
"""Minimum word frequency (Zipf scale, wordfreq) an NPC may use without it being in the scene's own vocabulary."""
MAX_RARE_WORDS = 1

_NUMBER = re.compile(r"\d+(?:[ ., ]\d{3})*(?:[.,]\d+)?")
_CAPITALISED = re.compile(r"(?<![.!?…«\"]\s)(?<!^)\b([A-ZÀ-ÖØ-Þ][\w'-]+)")


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105  (a verdict, not a password)
    REWRITE = "rewrite"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardResult:
    verdict: Verdict
    text: str
    reasons: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    """Rule path only (the ≤ 50 ms budget)."""
    claim_ms: float | None = None
    """Claim check, when one ran."""


class Rewriter(Protocol):
    async def simplify(self, sentence: str, band: int, language: str) -> str | None: ...


@dataclass(frozen=True)
class ClaimCheck:
    supported: bool
    repair: str | None = None
    """The sentence without its unsupported claims; ``None`` when nothing is left worth saying."""
    timed_out: bool = False


class ClaimChecker(Protocol):
    async def check(self, sentence: str, ctx: GuardContext) -> ClaimCheck: ...


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def _numbers(text: str, config: LanguageConfig) -> set[str]:
    found = {re.sub(r"[ ., ]", "", n) for n in _NUMBER.findall(text)}
    for token in words(text):
        if token in config.number_words:
            found.add(str(config.number_words[token]))
    return found


def zipf_floor(band: int) -> float:
    for max_band, floor in ZIPF_FLOOR_BY_BAND:
        if band <= max_band:
            return floor
    return 0.0


@dataclass
class GuardContext:
    """Precomputed per scene so each sentence check is set lookups only."""

    contract: SceneContract
    config: LanguageConfig
    allowed_text: str
    allowed_numbers: set[str] = field(default_factory=set)
    allowed_words: set[str] = field(default_factory=set)
    allowed_names: set[str] = field(default_factory=set)
    temporal_words: set[str] = field(default_factory=set)
    common_capitalised: set[str] = field(default_factory=set)
    grounding: list[str] = field(default_factory=list)
    """Everything the NPC may state, in sentences: the claim checker's world."""
    heard: list[str] = field(default_factory=list)
    """Learner lines, which the NPC may echo."""
    said: list[str] = field(default_factory=list)
    """The NPC's own delivered lines, which it may repeat."""
    known_words: set[str] = field(default_factory=set)
    """Words that carry no new claim: grounding, learner and earlier NPC lines, function words."""

    @classmethod
    def build(
        cls,
        contract: SceneContract,
        config: LanguageConfig,
        *,
        world_facts: list[str],
        names: list[str],
        scene_vocabulary: list[str],
        grounding: list[str] | None = None,
    ) -> GuardContext:
        allowed = " ".join([*contract.approved_facts, *world_facts, contract.learner_goal, *names, *scene_vocabulary])
        context = cls(
            contract=contract,
            config=config,
            allowed_text=allowed,
            grounding=grounding or [*contract.approved_facts, *world_facts],
        )
        context.allowed_numbers = _numbers(allowed, config)
        context.allowed_words = {_fold(w) for w in words(allowed)}
        context.allowed_names = {_fold(w) for name in names for w in words(name)}
        context.temporal_words = {_fold(w) for w in [*config.months, *config.weekdays]}
        context.common_capitalised = {_fold(w) for w in config.capitalised_common}
        context.known_words = context.allowed_words | {_fold(w) for w in words(" ".join(context.grounding))}
        context.known_words |= {_fold(w) for phrase in config.function_words for w in words(phrase)}
        return context

    def admit_learner_text(self, text: str) -> None:
        """Facts the learner introduces may be echoed back (e.g. a date they proposed)."""
        self.allowed_numbers |= _numbers(text, self.config)
        self.allowed_words |= {_fold(w) for w in words(text)}
        self.known_words |= {_fold(w) for w in words(text)}
        if text not in self.heard:
            self.heard.append(text)

    def admit_npc_text(self, text: str) -> None:
        if text:
            self.said.append(text)
            self.known_words |= {_fold(w) for w in words(text)}

    def needs_claim_check(self, sentence: str, short_words: int) -> bool:
        """False for a sentence of at most ``short_words`` words, or a question, that uses only known words: it can
        only recombine what is already grounded, so the slow check would add latency without catching anything."""
        tokens = [_fold(w) for w in words(sentence)]
        if any(t not in self.known_words for t in tokens):
            return True
        question = sentence.rstrip().endswith(tuple(self.config.question_marks))
        return len(tokens) > short_words and not question


class ContractGuard:
    def __init__(
        self,
        identifier: LanguageIdentifier,
        rewriter: Rewriter | None = None,
        claims: ClaimChecker | None = None,
        claim_free_words: int = 6,
        warm_languages: tuple[str, ...] = ("fr", "en"),
    ) -> None:
        self._identifier = identifier
        self._rewriter = rewriter
        self._claims = claims
        self._claim_free_words = claim_free_words
        self._patterns: dict[str, dict[str, list[re.Pattern[str]]]] = {}
        for language in warm_languages:
            zipf_frequency("bonjour", language)  # load frequency tables now, not on the first live sentence

    def _compiled(self, config: LanguageConfig) -> dict[str, list[re.Pattern[str]]]:
        if config.language not in self._patterns:
            self._patterns[config.language] = {
                "tutor": [re.compile(p, re.IGNORECASE) for p in config.tutor_markers],
                "character_break": [re.compile(p, re.IGNORECASE) for p in config.character_break_markers],
                "unsafe": [re.compile(p, re.IGNORECASE) for p in config.unsafe_markers],
            }
        return self._patterns[config.language]

    def check_rules(self, sentence: str, ctx: GuardContext) -> tuple[list[str], list[str]]:
        """(block reasons, rewrite reasons). Pure and synchronous: this is the ≤ 50 ms path."""
        block: list[str] = []
        rewrite: list[str] = []
        config = ctx.config
        patterns = self._compiled(config)
        for kind in ("unsafe", "character_break", "tutor"):
            if any(p.search(sentence) for p in patterns[kind]):
                block.append(kind)

        detected = self._identifier.identify(sentence)
        if detected is not None and detected != config.language:
            block.append("wrong_language")

        stray_numbers = _numbers(sentence, config) - ctx.allowed_numbers
        if stray_numbers:
            block.append(f"off_contract_number:{','.join(sorted(stray_numbers))}")
        tokens = [_fold(w) for w in words(sentence)]
        stray_time = [t for t in tokens if t in ctx.temporal_words and t not in ctx.allowed_words]
        if stray_time:
            block.append(f"off_contract_date:{','.join(stray_time)}")
        known = ctx.allowed_names | ctx.allowed_words | ctx.common_capitalised
        for match in _CAPITALISED.finditer(sentence):
            # Hyphenated names ("Vieux-Port", "Jean-Marc") are matched whole but stored word by word.
            if not all(_fold(part) in known for part in words(match.group(1))):
                block.append(f"off_contract_name:{match.group(1)}")

        floor = zipf_floor(ctx.contract.npc_language_band)
        if floor:
            rare = [
                t
                for t in tokens
                if len(t) > 3 and t not in ctx.allowed_words and zipf_frequency(t, config.language) < floor
            ]
            if len(rare) > MAX_RARE_WORDS:
                rewrite.append(f"over_band:{','.join(rare)}")
        return block, rewrite

    def will_check_claims(self, screened: GuardResult, ctx: GuardContext) -> bool:
        if self._claims is None or screened.verdict is Verdict.BLOCK:
            return False
        return ctx.needs_claim_check(screened.text, self._claim_free_words)

    async def check(self, sentence: str, ctx: GuardContext) -> GuardResult:
        return await self.confirm(await self.screen(sentence, ctx), ctx)

    async def confirm(self, result: GuardResult, ctx: GuardContext) -> GuardResult:
        """Claim check of a screened sentence (a no-op without a checker or when the rules already blocked it)."""
        if self._claims is None or not self.will_check_claims(result, ctx):
            return result
        started = time.perf_counter()
        claim = await self._claims.check(result.text, ctx)
        claim_ms = (time.perf_counter() - started) * 1000
        if claim.supported:
            return replace(result, claim_ms=claim_ms)
        reasons = (*result.reasons, "claim_check_timeout" if claim.timed_out else "unsupported_claim")
        if claim.repair and is_complete(claim.repair):
            again_block, again_rewrite = self.check_rules(claim.repair, ctx)
            if not again_block and not again_rewrite:
                return GuardResult(Verdict.REWRITE, claim.repair, reasons, result.elapsed_ms, claim_ms)
        return GuardResult(Verdict.BLOCK, result.text, reasons, result.elapsed_ms, claim_ms)

    async def screen(self, sentence: str, ctx: GuardContext) -> GuardResult:
        """Rules, plus the over-band rewrite when one is needed."""
        started = time.perf_counter()
        block, rewrite = self.check_rules(sentence, ctx)
        rule_ms = (time.perf_counter() - started) * 1000
        if block:
            return GuardResult(Verdict.BLOCK, sentence, tuple(block), rule_ms)
        if not rewrite:
            return GuardResult(Verdict.PASS, sentence, (), rule_ms)
        if self._rewriter is None:
            return GuardResult(Verdict.BLOCK, sentence, tuple(rewrite), rule_ms)
        simpler = await self._rewriter.simplify(sentence, ctx.contract.npc_language_band, ctx.config.language)
        if simpler:
            again_block, again_rewrite = self.check_rules(simpler, ctx)
            if not again_block and not again_rewrite:
                elapsed = (time.perf_counter() - started) * 1000
                return GuardResult(Verdict.REWRITE, simpler, tuple(rewrite), elapsed)
        return GuardResult(Verdict.BLOCK, sentence, tuple(rewrite), (time.perf_counter() - started) * 1000)
