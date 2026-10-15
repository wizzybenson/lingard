"""Claim check for the Contract Guard (SPEC §10 "small classifier", decision 0012).

A small model on the ``guard`` tier reads one NPC sentence against everything the NPC may state and answers ``OK``
or ``FIX: <repaired sentence>``. The scene's grounding is the cached system prefix, so a check costs the dialogue so
far plus one sentence. A check that fails or misses its deadline counts as unsupported: a silent sentence is safer
than an invented procedure.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import HumanMessage

from lingard_contracts.common import LANGUAGE_NAME
from lingard_live.guard import ClaimCheck, GuardContext
from lingard_llm import LLMRouter, Prompt
from lingard_llm.router import cached_system

logger = logging.getLogger(__name__)
_NOTHING_LEFT = {"none", ""}


def parse_answer(raw: str) -> ClaimCheck:
    """``OK`` → supported; ``FIX: text`` → unsupported with a repair; anything else is treated as unsupported."""
    line = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    if line.upper().rstrip(".") == "OK":
        return ClaimCheck(supported=True)
    if line.upper().startswith("FIX:"):
        repair = line[4:].strip().strip('"«» ')
        return ClaimCheck(supported=False, repair=None if repair.casefold() in _NOTHING_LEFT else repair)
    return ClaimCheck(supported=False)


class LlmClaimChecker:
    def __init__(self, router: LLMRouter, prompt: Prompt, *, deadline_s: float, context_lines: int) -> None:
        """``context_lines``: how many recent lines from each speaker the check sees."""
        self._router = router
        self._prompt = prompt
        self._deadline_s = deadline_s
        self._context_lines = context_lines

    def _system(self, ctx: GuardContext) -> str:
        return self._prompt.render(
            facts="\n".join(f"- {fact}" for fact in ctx.grounding), language_name=LANGUAGE_NAME[ctx.config.language]
        )

    async def check(self, sentence: str, ctx: GuardContext) -> ClaimCheck:
        heard = " | ".join(ctx.heard[-self._context_lines :]) or "(nothing yet)"
        said = " | ".join(ctx.said[-self._context_lines :]) or "(nothing yet)"
        user = f"The other speaker said: {heard}\nThe character already said: {said}\n\nSentence to check: {sentence}"
        messages = [
            cached_system(self._system(ctx), self._router.primary_provider("guard")),
            HumanMessage(content=user),
        ]
        try:
            raw = await asyncio.wait_for(self._router.text("guard", self._prompt, messages), self._deadline_s)
        except Exception:  # a timeout or provider error: fail closed, the scene goes on
            logger.warning("claim check failed; withholding the sentence", exc_info=True)
            return ClaimCheck(supported=False, timed_out=True)
        return parse_answer(raw)


class ScriptedClaimChecker:
    """Offline checker for tests and benchmarks: listed sentences get their scripted answer, the rest are supported."""

    def __init__(self, answers: dict[str, ClaimCheck] | None = None, delay_ms: float = 0) -> None:
        self.answers = answers or {}
        self.delay_ms = delay_ms
        self.checked: list[str] = []

    async def check(self, sentence: str, ctx: GuardContext) -> ClaimCheck:
        self.checked.append(sentence)
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        return self.answers.get(sentence, ClaimCheck(supported=True))
