import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from lingard_api import coaching
from lingard_api.coach import Signals, Sound
from lingard_graphs.agents.learning_coach import CoachBrief, SoundCandidate

SIGNALS = Signals(story_ready=True, sounds=(Sound("fr.pron.u_vs_ou", "/y/ et /u/", "rue"),))
BRIEF = CoachBrief(
    language="fr",
    band=6,
    exam_name="TEF Canada",
    explain_language="English",
    sounds=[SoundCandidate(drill="fr.pron.u_vs_ou", title="/y/ et /u/", score=None)],
)


async def test_a_failing_coach_is_not_asked_again_on_every_look(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def failing(*_: Any, **__: Any) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider down")

    async def gather(*_: Any) -> Any:
        return SimpleNamespace(signals=SIGNALS, today=datetime.now(UTC).date())

    async def brief(*_: Any) -> CoachBrief:
        return BRIEF

    monkeypatch.setattr(coaching, "_gather", gather)
    monkeypatch.setattr(coaching, "_brief", brief)
    monkeypatch.setattr(coaching, "ask_coach", failing)
    monkeypatch.setattr(coaching, "any_llm_configured", lambda: True)
    prompts = SimpleNamespace(get=lambda _: SimpleNamespace(ref="learning_coach@v3", template="…"))
    state: Any = SimpleNamespace(graph_deps=SimpleNamespace(prompts=prompts, router=None))
    user: Any = SimpleNamespace(id=uuid.uuid4())
    profile: Any = SimpleNamespace(settings={})
    db: Any = None

    async def look() -> str:
        view = await coaching.todays_path(
            state, db, user, profile, "fr", story_ready=True, reviews_due=0, skills={}, exam_name="TEF Canada"
        )
        await asyncio.sleep(0)  # let the background ask run
        return view.source

    assert await look() == "thinking"
    assert [await look() for _ in range(5)] == ["rules"] * 5, "after a failure the path stands without asking"
    assert calls == 1, "an outage costs one call, not one per look"
