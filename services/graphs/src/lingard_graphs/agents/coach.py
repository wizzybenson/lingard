"""Coach (SPEC §10): the night notebook. Only confirmed corrections (≥ 0.85 and second check) are ever shown."""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from lingard_contracts.assessment import ErrorTag, UtteranceAssessment
from lingard_contracts.common import LANGUAGE_NAME
from lingard_curriculum.models import CurriculumNode
from lingard_llm import LLMRouter, PromptRegistry, StructuredOutputError


class NotebookItem(BaseModel):
    node_key: str
    learner_said: str
    correction: str
    explanation: str


class Notebook(BaseModel):
    corrections: list[NotebookItem]
    strengths: list[str]
    encouragement: str
    review_items: list[str]
    lessons_suggested: list[str]


class _Written(BaseModel):
    class Item(BaseModel):
        index: int
        explanation: str

    items: list[Item]
    encouragement: str


def confirmed_corrections(assessments: list[UtteranceAssessment]) -> list[ErrorTag]:
    """Showable tags only, one per node and span (the strongest)."""
    best: dict[tuple[str, str], ErrorTag] = {}
    for assessment in assessments:
        for tag in assessment.error_tags:
            if not tag.showable or not tag.correction:
                continue
            key = (tag.node_key, tag.span.text.casefold())
            if key not in best or tag.confidence > best[key].confidence:
                best[key] = tag
    return sorted(best.values(), key=lambda t: -t.confidence)


class Coach:
    def __init__(self, router: LLMRouter, prompts: PromptRegistry, max_items: int = 6) -> None:
        self._router = router
        self._prompt = prompts.get("coach_notebook")
        self._max = max_items

    async def notebook(
        self,
        assessments: list[UtteranceAssessment],
        nodes: dict[str, CurriculumNode],
        *,
        language: str,
        ui_language: str,
        band: int,
        lessons_suggested: list[str],
        trace_id: str | None = None,
    ) -> Notebook:
        tags = confirmed_corrections(assessments)[: self._max]
        strengths = sorted({e.node_key for a in assessments for e in a.target_evidence if e.correct})
        rules = {
            t.node_key: (nodes[t.node_key].payload.get("lesson") or {}).get("rule", nodes[t.node_key].title)
            if t.node_key in nodes
            else ""
            for t in tags
        }
        fallback = {i: t.explanation or rules[t.node_key] for i, t in enumerate(tags)}
        encouragement = ""
        if tags or strengths:
            listing = "\n".join(
                f'{i}. said "{t.span.text}" → "{t.correction}" (rule: {rules[t.node_key]})' for i, t in enumerate(tags)
            )
            text = self._prompt.render(
                language_name=LANGUAGE_NAME[language],
                ui_language=LANGUAGE_NAME.get(ui_language, "English"),
                corrections=listing or "none",
                band=band,
                strengths=", ".join(nodes[k].title for k in strengths if k in nodes) or "showing up and trying",
            )
            try:
                written = await self._router.structured(
                    "frontier", self._prompt, _Written, [HumanMessage(content=text)], trace_id=trace_id
                )
                for item in written.items:
                    if 0 <= item.index < len(tags) and item.explanation.strip():
                        fallback[item.index] = item.explanation.strip()
                encouragement = written.encouragement
            except StructuredOutputError:
                encouragement = ""
        return Notebook(
            corrections=[
                NotebookItem(
                    node_key=t.node_key,
                    learner_said=t.span.text,
                    correction=t.correction or "",
                    explanation=fallback[i],
                )
                for i, t in enumerate(tags)
            ],
            strengths=strengths,
            encouragement=encouragement,
            review_items=sorted({t.node_key for t in tags}),
            lessons_suggested=lessons_suggested,
        )
