"""``contract_adherence`` (SPEC §20): fact violations 0, language leaks 0, targets elicited ≥ 85%.

Offline: 50 scenes × planted violations and clean lines through the real Contract Guard (no LLM).
Live: real actor + simulated learner per scene; an independent judge checks delivered lines (needs any LLM key).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import yaml

from evals.framework import ROOT, Gate, Mode, SuiteResult, suite
from evals.scenes import eval_scenes
from lingard_live.guard import ContractGuard, Verdict
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.scene import build_scene
from lingard_llm.config import any_llm_configured
from lingard_world import load_city

GATES = [
    Gate("fact_violations_leaked", "==", 0),
    Gate("language_leaks", "==", 0),
    Gate("false_block_rate", "<=", 0.05),
]


def _sentences(language: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / f"evals/datasets/guard/{language}.yaml").read_text())
    return data


def _on_contract(violation: dict[str, str], allowed_text: str) -> bool:
    """A planted fact whose ``key`` the scene legitimately knows (e.g. a weekday in an NPC's world facts) isn't a
    violation in that scene, so it is skipped rather than counted as a leak."""
    key = violation.get("key")
    return key is not None and re.search(rf"\b{re.escape(key)}\b", allowed_text, re.IGNORECASE) is not None


async def offline() -> SuiteResult:
    content = ROOT / "content"
    identifier = LanguageIdentifier([load_language(content, "fr"), load_language(content, "en")])
    guard = ContractGuard(identifier)
    leaked: Counter[str] = Counter()
    wrong_reason = 0
    clean_total = clean_blocked = violation_total = on_contract = 0
    samples: list[dict[str, object]] = []
    for contract, _, amount in eval_scenes(50):
        runtime = build_scene(contract, content, learner_name="Ernest")
        npc_first = load_city(content, contract.city).npc(contract.cast[0].npc_key).name.split()[0]
        lines = _sentences(contract.language)
        for template in lines["clean"]:
            text = template.format(learner="Ernest", npc=npc_first, fact_number=amount)
            result = await guard.check(text, runtime.guard_ctx)
            clean_total += 1
            if result.verdict is Verdict.BLOCK:
                clean_blocked += 1
                samples.append({"kind": "false_block", "text": text, "reasons": list(result.reasons)})
        for violation in lines["violations"]:
            if _on_contract(violation, runtime.guard_ctx.allowed_text):
                on_contract += 1
                continue
            result = await guard.check(violation["text"], runtime.guard_ctx)
            violation_total += 1
            if result.verdict is not Verdict.BLOCK:
                leaked[violation["reason"]] += 1
                samples.append({"kind": "leak", "text": violation["text"], "expected": violation["reason"]})
            elif not any(r.startswith(violation["reason"]) for r in result.reasons):
                wrong_reason += 1
    fact_reasons = ("off_contract_number", "off_contract_date", "off_contract_name")
    return SuiteResult(
        suite="contract_adherence",
        mode="offline",
        metrics={
            "scenes": 50,
            "violations_planted": violation_total,
            "plants_skipped_on_contract": on_contract,
            "fact_violations_leaked": sum(leaked[r] for r in fact_reasons),
            "language_leaks": leaked["wrong_language"],
            "tutor_or_break_leaks": leaked["tutor"] + leaked["character_break"],
            "blocked_for_wrong_reason": wrong_reason,
            "clean_lines": clean_total,
            "false_block_rate": round(clean_blocked / clean_total, 4),
        },
        gates=GATES,
        notes=["Offline mode checks the Guard against planted violations; targets-elicited needs live mode."],
        samples=samples,
    )


async def live() -> SuiteResult:
    from evals.live_scenes import run_live_scenes

    return await run_live_scenes(scene_count=50)


@suite("contract_adherence", watches=("services/live/", "content/languages/", "prompts/npc_actor/", "content/cities/"))
async def run(mode: Mode) -> SuiteResult:
    if mode == "live":
        if not any_llm_configured():
            return SuiteResult("contract_adherence", "live", {}, GATES, notes=["skipped: no LLM provider key set"])
        return await live()
    return await offline()
