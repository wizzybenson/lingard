"""LLM item generation per task type (original content, difficulty-tagged), validated before entering the bank."""

from __future__ import annotations

import hashlib

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_SCALE, Skill
from lingard_curriculum.packs import ExamPack
from lingard_exam_packs.items import Item
from lingard_llm import LLMRouter, PromptRegistry

EXAMS = {"tef_canada": "TEF Canada", "ielts_gt": "IELTS General Training"}
INSTRUCTIONS = {
    Skill.READING: "stimulus: a short authentic-looking document (notice, email, article extract) of 25–120 words.",
    Skill.LISTENING: "stimulus: a natural spoken script (announcement, voicemail, dialogue, radio) of 20–90 words.",
}


class _Raw(BaseModel):
    stimulus: str = Field(min_length=10)
    question: str = Field(min_length=5)
    options: list[str] = Field(min_length=4, max_length=4)
    answer: int


class _Batch(BaseModel):
    items: list[_Raw]


class ItemGenerator:
    def __init__(self, router: LLMRouter, prompts: PromptRegistry) -> None:
        self._router = router
        self._prompt = prompts.get("item_generator")

    async def generate(
        self,
        pack: ExamPack,
        skill: Skill,
        band: int,
        count: int,
        *,
        avoid: list[str] | None = None,
        trace_id: str | None = None,
    ) -> list[Item]:
        if skill not in INSTRUCTIONS:
            raise ValueError(f"no generator for {skill}")
        section = pack.section_for(skill)
        text = self._prompt.render(
            count=count,
            skill=skill.value,
            exam=EXAMS[pack.id],
            section=section.id,
            language_name=LANGUAGE_NAME[pack.language],
            scale_name=LANGUAGE_SCALE[pack.language],
            band=band,
            skill_instructions=INSTRUCTIONS[skill],
            avoid="; ".join(avoid or []) or "none",
        )
        batch = await self._router.structured(
            "mid", self._prompt, _Batch, [HumanMessage(content=text)], trace_id=trace_id
        )
        items = []
        for raw in batch.items:
            digest = hashlib.sha256(f"{pack.id}|{raw.stimulus}|{raw.question}".encode()).hexdigest()[:12]
            try:
                items.append(
                    Item(
                        id=f"gen-{pack.id}-{skill.value}-{digest}",
                        pack=pack.id,
                        language=pack.language,
                        skill=skill,
                        section=section.id,
                        task_type=f"{section.id}_generated",
                        band=band,
                        stimulus=raw.stimulus,
                        question=raw.question,
                        options=raw.options,
                        answer=raw.answer,
                        source="generated",
                    )
                )
            except ValidationError:
                continue  # malformed items are dropped, never repaired silently
        return items
