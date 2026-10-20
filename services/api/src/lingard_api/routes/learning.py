"""``/v1``: placement, Exam Hall, writing, lessons and the Passport (bands always shown with their range)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.deps import Db, Principal, State
from lingard_api.graph_runtime import Step, ThreadAccessError
from lingard_api.jobs import GRAPH_JOBS
from lingard_api.routes.speech import narrate, require_providers, wav_response
from lingard_api.state import AppState
from lingard_contracts.assessment import BandEstimate
from lingard_contracts.common import LANGUAGE_CITY, LANGUAGE_PACK, Language, PackId, Skill, node_language
from lingard_db.models import BandPosterior, Lesson, SimCrsSnapshot, WritingSubmission
from lingard_economy.crs import DISCLAIMER
from lingard_economy.rewards import COINS, LedgerEntry
from lingard_graphs.pedagogy.bands import BandPosterior as Posterior
from lingard_graphs.pedagogy.bands import summarise
from lingard_graphs.pedagogy.review import new_card, review

router = APIRouter(prefix="/v1", tags=["learning"])
LESSON_PASS = 0.7


class StepView(BaseModel):
    thread_id: str
    done: bool
    prompt: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    @classmethod
    def of(cls, step: Step) -> StepView:
        result = None
        if step.result is not None:
            allowed = ("estimates", "start_district", "status", "scores", "levels", "overall", "mock_id")
            result = {k: v for k, v in step.result.items() if k in allowed}
        return cls(thread_id=step.thread_id, done=step.done, prompt=step.prompt, result=result)


class PlacementBody(BaseModel):
    language: Language
    path: Literal["quick", "mock", "skip"] = "quick"
    in_fiction: bool = True


class ExamBody(BaseModel):
    pack: PackId


class AnswerBody(BaseModel):
    value: Any


class WritingBody(BaseModel):
    pack: PackId
    task_id: str
    prompt: str
    text: str


class PassportView(BaseModel):
    bands: list[BandEstimate]
    sim_crs: int | None
    crs_breakdown: dict[str, Any] | None
    disclaimer: str = DISCLAIMER


def _interactive(state: State) -> Any:
    if state.interactive is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "graphs are starting")
    return state.interactive


@router.post("/placement", response_model=StepView, status_code=201)
async def start_placement(body: PlacementBody, principal: Principal, state: State) -> StepView:
    if body.path != "skip":
        require_providers(state, llm=True, tts=True)
    step = await _interactive(state).start("placement", principal.user_id, body.model_dump())
    return StepView.of(step)


class SectionFormat(BaseModel):
    id: str
    skill: Skill
    minutes: int
    """The longest the section can take (IELTS Speaking: 11–14 minutes → 14)."""
    questions: int | None
    """Scored questions (reading and listening); writing and speaking have tasks or parts instead."""
    tasks: int


class ExamFormat(BaseModel):
    pack: PackId
    name: str
    total_minutes: int
    sections: list[SectionFormat]


@router.get("/exams/formats", response_model=list[ExamFormat])
async def exam_formats(principal: Principal, state: State) -> list[ExamFormat]:
    """Each exam in its official order, as a full mock runs it (pack.yaml)."""
    formats = []
    for pack_id in ("tef_canada", "ielts_gt"):
        pack = state.packs.pack(pack_id)
        sections = [
            SectionFormat(
                id=s.id,
                skill=s.skill,
                minutes=s.max_minutes,
                questions=s.items,
                tasks=len(s.tasks) or len(s.part_list()),
            )
            for s in pack.ordered_sections()
        ]
        formats.append(
            ExamFormat(pack=pack.id, name=pack.name, total_minutes=sum(s.minutes for s in sections), sections=sections)
        )
    return formats


@router.post("/exams", response_model=StepView, status_code=201)
async def start_exam(body: ExamBody, principal: Principal, state: State) -> StepView:
    require_providers(state, llm=True, tts=True)
    return StepView.of(await _interactive(state).start("exam", principal.user_id, body.model_dump()))


@router.post("/threads/{thread_id}/answer", response_model=StepView)
async def answer(thread_id: str, body: AnswerBody, principal: Principal, state: State) -> StepView:
    try:
        return StepView.of(await _interactive(state).resume(thread_id, principal.user_id, body.value))
    except ThreadAccessError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such thread") from exc


@router.post("/writing", status_code=202)
async def submit_writing(body: WritingBody, principal: Principal, state: State) -> dict[str, str]:
    require_providers(state, llm=True)
    pack = state.packs.pack(body.pack)
    if not any(t.id == body.task_id for s in pack.sections for t in s.tasks):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{body.pack} has no task {body.task_id}")
    job_id = await state.jobs.enqueue(
        GRAPH_JOBS,
        {
            "kind": "writing_review",
            "user_id": principal.user_id,
            "pack": body.pack,
            "task_id": body.task_id,
            "task_prompt": body.prompt,
            "text": body.text,
        },
    )
    await state.graph_deps.store.mark_active(principal.user_id, datetime.now(UTC).date())
    return {"status": "scoring", "job_id": job_id}


class WritingTask(BaseModel):
    pack: PackId
    pack_name: str
    task_id: str
    kind: str
    min_words: int
    suggested_minutes: int
    prompts: list[str]


@router.get("/writing/tasks", response_model=list[WritingTask])
async def writing_tasks(principal: Principal, state: State) -> list[WritingTask]:
    """Every writing task of every pack, with practice prompts from ``content/packs/<pack>/writing_prompts.yaml``."""
    tasks = []
    for pack_id in LANGUAGE_PACK.values():
        pack = state.packs.pack(pack_id)
        prompts = _writing_prompts(state.settings.content_root, pack_id)
        for task in pack.section_for(Skill.WRITING).tasks:
            tasks.append(
                WritingTask(
                    pack=pack_id,
                    pack_name=pack.name,
                    task_id=task.id,
                    kind=task.kind,
                    min_words=task.min_words,
                    suggested_minutes=task.suggested_minutes,
                    prompts=prompts.get(task.id, []),
                )
            )
    return tasks


@cache
def _writing_prompts(content_root: Path, pack_id: str) -> dict[str, list[str]]:
    path = content_root / "packs" / pack_id / "writing_prompts.yaml"
    data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    return {str(k): [str(p) for p in v] for k, v in (data or {}).items()}


@router.get("/writing")
async def list_writing(principal: Principal, db: Db) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(WritingSubmission)
        .where(WritingSubmission.user_id == principal.user_id)
        .order_by(WritingSubmission.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": r.id,
            "pack": r.pack,
            "task_type": r.task_type,
            "word_count": r.word_count,
            "scores": r.scores,
            "rewrite": r.rewrite,
            "created_at": r.created_at,
        }
        for r in rows.scalars()
    ]


@router.get("/lessons")
async def list_lessons(principal: Principal, db: Db) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Lesson).where(Lesson.user_id == principal.user_id).order_by(Lesson.created_at.desc())
    )
    return [{"id": r.id, "node_key": r.node_key, "status": r.status, "content": r.content} for r in rows.scalars()]


@router.post("/lessons/{node_key}", status_code=202)
async def request_lesson(node_key: str, principal: Principal, state: State) -> dict[str, str]:
    city = LANGUAGE_CITY[node_language(node_key)]
    job_id = await state.jobs.enqueue(
        GRAPH_JOBS, {"kind": "lesson_builder", "user_id": principal.user_id, "node_key": node_key, "city": city}
    )
    return {"status": "building", "job_id": job_id}


@router.get("/passport", response_model=PassportView)
async def passport(principal: Principal, state: State, db: Db) -> PassportView:
    bands = await learner_bands(state, db, principal.user_id)
    snapshot = (
        await db.execute(
            select(SimCrsSnapshot)
            .where(SimCrsSnapshot.user_id == principal.user_id)
            .order_by(SimCrsSnapshot.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return PassportView(
        bands=bands,
        sim_crs=snapshot.value if snapshot else None,
        crs_breakdown=snapshot.breakdown if snapshot else None,
    )


async def learner_bands(state: AppState, db: AsyncSession, user_id: uuid.UUID) -> list[BandEstimate]:
    """Every band posterior summarised with its 80% range and CLB/NCLC levels, sorted by pack then skill."""
    rows = (await db.execute(select(BandPosterior).where(BandPosterior.user_id == user_id))).scalars()
    rules = state.graph_deps.pedagogy.bands
    bands = []
    for row in rows:
        pack_id: PackId = row.pack  # type: ignore[assignment]
        skill = Skill(row.skill)
        bands.append(
            summarise(
                Posterior(row.mean, row.variance, row.observations),
                state.packs.pack(pack_id),
                skill,
                state.packs.conversion(pack_id),
                rules,
                pack_id,
            )
        )
    return sorted(bands, key=lambda b: (b.pack, b.skill.value))


class LessonResult(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(gt=0)


@router.post("/lessons/{lesson_id}/complete")
async def complete_lesson(
    lesson_id: uuid.UUID, body: LessonResult, principal: Principal, state: State, db: Db
) -> dict[str, Any]:
    """A finished lesson counts as one review of its node (passed at ≥ 70%) and pays the lesson reward once."""
    row = await db.get(Lesson, lesson_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such lesson")
    passed = body.correct / body.total >= LESSON_PASS
    store = state.graph_deps.store
    if row.status != "done":
        card = (await store.fsrs(principal.user_id)).get(row.node_key) or new_card()
        await store.save_fsrs(principal.user_id, row.node_key, review(card, passed))
        reward = LedgerEntry("coins", COINS["lesson_complete"], "lesson_complete", str(row.id), f"lesson:{row.id}")
        await store.apply_ledger(principal.user_id, [reward])
        row.status = "done"
        row.content = {**row.content, "result": body.model_dump()}
        await db.commit()
    await store.mark_active(principal.user_id, datetime.now(UTC).date())
    return {"status": row.status, "passed": passed}


@router.get("/lessons/{lesson_id}/audio")
async def lesson_audio(
    lesson_id: uuid.UUID, game: int, item: int, principal: Principal, state: State, db: Db
) -> Response:
    """Dictation and listening games: the item is spoken by the narrator, never sent as text first."""
    row = await db.get(Lesson, lesson_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such lesson")
    try:
        sentence = str(row.content["games"][game]["items"][item]["answer"])
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game item") from exc
    try:
        pcm = await narrate(state, sentence, node_language(row.node_key))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return wav_response(pcm)


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, principal: Principal, db: Db) -> dict[str, Any]:
    row = await db.get(Lesson, lesson_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such lesson")
    return {"id": row.id, "node_key": row.node_key, "status": row.status, "content": row.content}
