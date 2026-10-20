"""Machine review of the curriculum's lessons (rules, word sets, phrase sets) by a native-speaker teacher prompt.

Run: ``python -m tools.content_cli.review_lessons fr [--kinds grammar,lexset,function] [--keys k1,k2]``.

Writes ``evals/results/lesson_review.<lang>.json`` with one verdict per node and prints the problems found. It is a
check before a person reads the content, not a replacement for one: an LLM reviewer can share an LLM author's blind
spots. Paid (the ``mid`` tier, one call per node); about 0.003 USD a node.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from lingard_contracts.common import LANGUAGE_NAME, Language
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.seed import load_seed
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry

ROOT = Path(__file__).resolve().parents[2]
EXAMS = {"fr": "TEF Canada", "en": "IELTS General Training"}
REGIONS = {"fr": "Canada (Québec) and France", "en": "the United Kingdom"}
CONCURRENCY = 6


class Problem(BaseModel):
    part: Literal["rule", "model", "mistake"]
    text: str
    issue: str
    suggestion: str


class LessonVerdict(BaseModel):
    verdict: Literal["ok", "fix"]
    problems: list[Problem] = []


def describe(node: CurriculumNode) -> str:
    lesson = node.payload["lesson"]
    lines = [f"Title: {node.title} (level CLB/NCLC {node.band})", f"Rule: {lesson['rule']}", "Models:"]
    lines += [f"- {m}" for m in lesson["examples"]]
    lines.append("Common mistakes (wrong → right):")
    lines += [f"- {e['wrong']} → {e['right']}" for e in lesson["common_errors"]]
    return "\n".join(lines)


async def review(
    nodes: list[CurriculumNode], language: Language, router: LLMRouter, prompts: PromptRegistry
) -> dict[str, LessonVerdict]:
    prompt = prompts.get("lesson_review")
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(node: CurriculumNode) -> tuple[str, LessonVerdict]:
        system, per_call = prompt.render_split(
            language_name=LANGUAGE_NAME[language],
            exam=EXAMS[language],
            region=REGIONS[language],
            lesson=describe(node),
        )
        async with gate:
            verdict = await router.structured("mid", prompt, LessonVerdict, router.messages("mid", system, per_call))
        return node.key, verdict

    return dict(await asyncio.gather(*(one(n) for n in nodes)))


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("language", choices=["fr", "en"])
    parser.add_argument("--kinds", default="grammar,lexset,function")
    parser.add_argument("--keys", default="", help="only these node keys (comma-separated)")
    args = parser.parse_args()
    language: Language = args.language
    kinds, keys = set(args.kinds.split(",")), {k for k in args.keys.split(",") if k}
    nodes = [
        n
        for n in load_seed(ROOT / "content", language).nodes
        if n.kind in kinds and "lesson" in n.payload and (not keys or n.key in keys)
    ]
    router = LLMRouter(LLMConfig.load(ROOT / "config" / "llm.yaml"))
    verdicts = asyncio.run(review(nodes, language, router, PromptRegistry(ROOT / "prompts")))
    out = ROOT / "evals" / "results" / f"lesson_review.{language}.json"
    out.write_text(json.dumps({k: v.model_dump() for k, v in verdicts.items()}, ensure_ascii=False, indent=2) + "\n")
    flagged = {k: v for k, v in verdicts.items() if v.verdict == "fix"}
    for key, verdict in flagged.items():
        for p in verdict.problems:
            print(f"{key} [{p.part}] {p.text}\n    {p.issue}\n    → {p.suggestion}")
    print(f"{len(flagged)} of {len(verdicts)} lessons flagged; written to {out}", file=sys.stderr)
    print(f"spend: {router.sink.total_cost():.2f} USD", file=sys.stderr)  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
