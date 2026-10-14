"""``/v1``: placement, Exam Hall, writing, lessons and the Passport (bands always shown with their range)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from lingard_api.deps import Db, Principal, State
from lingard_api.graph_runtime import Step, ThreadAccessError
from lingard_api.jobs import GRAPH_JOBS
from lingard_api.routes.speech import require_providers
from lingard_contracts.assessment import BandEstimate
from lingard_contracts.common import LANGUAGE_CITY, Language, PackId, Skill, node_language
from lingard_db.models import BandPosterior, Lesson, SimCrsSnapshot, WritingSubmission
from lingard_economy.crs import DISCLAIMER
from lingard_graphs.pedagogy.bands import BandPosterior as Posterior
from lingard_graphs.pedagogy.bands import summarise

router = APIRouter(prefix="/v1", tags=["learning"])


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
    return {"status": "scoring", "job_id": job_id}


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
    rows = (await db.execute(select(BandPosterior).where(BandPosterior.user_id == principal.user_id))).scalars()
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
    snapshot = (
        await db.execute(
            select(SimCrsSnapshot)
            .where(SimCrsSnapshot.user_id == principal.user_id)
            .order_by(SimCrsSnapshot.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return PassportView(
        bands=sorted(bands, key=lambda b: (b.pack, b.skill.value)),
        sim_crs=snapshot.value if snapshot else None,
        crs_breakdown=snapshot.breakdown if snapshot else None,
    )


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, principal: Principal, db: Db) -> dict[str, Any]:
    row = await db.get(Lesson, lesson_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such lesson")
    return {"id": row.id, "node_key": row.node_key, "status": row.status, "content": row.content}
