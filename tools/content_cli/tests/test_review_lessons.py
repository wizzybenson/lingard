import json
from pathlib import Path

from lingard_curriculum.seed import load_seed
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_llm.testing import ScriptedChatModel
from tools.content_cli.review_lessons import describe, review

ROOT = Path(__file__).resolve().parents[3]


async def test_each_lesson_gets_one_verdict_and_problems_are_kept() -> None:
    nodes = [n for n in load_seed(ROOT / "content", "fr").nodes if n.key in ("fr.lex.banking", "fr.func.telephone")]
    replies = iter(
        [
            {"verdict": "ok"},
            {"verdict": "fix", "problems": [{"part": "model", "text": "x", "issue": "unnatural", "suggestion": "y"}]},
        ]
    )
    model = ScriptedChatModel(responder=lambda _: json.dumps(next(replies)))
    config = LLMConfig.model_validate({"tiers": {"mid": {"models": [{"provider": "scripted", "model": "teacher"}]}}})
    verdicts = await review(
        nodes, "fr", LLMRouter(config, factory=lambda _spec: model), PromptRegistry(ROOT / "prompts")
    )
    assert set(verdicts) == {"fr.lex.banking", "fr.func.telephone"}
    assert sorted(v.verdict for v in verdicts.values()) == ["fix", "ok"]
    assert "Common mistakes (wrong → right):" in describe(nodes[0]) and "Rule:" in describe(nodes[0])
