"""``/v1/sessions`` and ``/v1/scenes``: plan a day, read scenes (visible parts only), go live."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from lingard_api.deps import Db, Principal, State
from lingard_api.jobs import GRAPH_JOBS, LIVE_JOBS
from lingard_api.livekit_token import mint_learner_token
from lingard_api.routes.speech import require_providers
from lingard_contracts.common import CITY_LANGUAGE, CityKey
from lingard_contracts.scene import SceneContract
from lingard_db.models import LearnerProfile, Scene, Session, User
from lingard_llm.config import any_llm_configured
from lingard_world import load_city

router = APIRouter(prefix="/v1", tags=["sessions"])


class StartSessionBody(BaseModel):
    city: CityKey
    kind: Literal["live", "glance"] = "live"


class SessionView(BaseModel):
    id: uuid.UUID
    city: str | None
    kind: str
    status: Literal["planning", "ready", "failed", "ended"]
    scene_ids: list[uuid.UUID]
    complete: bool = False
    """Every scene of the day is compiled. A ready day may start before this: later scenes keep arriving."""
    error: str | None = None
    notebook: dict[str, Any] | None = None


class SceneView(BaseModel):
    """What the learner may see: never the hidden targets, tactics or evidence specs (SPEC §9)."""

    id: uuid.UUID
    city: str
    location_key: str
    npc_keys: list[str]
    learner_goal: str
    status: str
    intensity: str
    location_name: str = ""
    layer_art: list[str] = []
    npc_name: str = ""
    npc_role: str = ""
    learner_band: int | None = None
    """The learner's band in the scene's language; captions fade as it rises (SPEC §11)."""


class LiveTicket(BaseModel):
    livekit_url: str
    room: str
    token: str
    scene_id: uuid.UUID


def scene_view(row: Scene) -> SceneView:
    contract = SceneContract.model_validate(row.contract)
    return SceneView(
        id=row.id,
        city=contract.city,
        location_key=contract.location_key,
        npc_keys=[c.npc_key for c in contract.cast],
        learner_goal=contract.learner_goal,
        status=row.status,
        intensity=contract.intensity,
    )


async def _owned_session(db: Db, principal: Principal, session_id: uuid.UUID) -> Session:
    row = await db.get(Session, session_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such session")
    return row


async def _reusable_day(db: Db, user_id: uuid.UUID, city: str, kind: str, state: State) -> Session | None:
    """The newest unended day for this city that is still planning, or planned and not played yet. A planned day
    waits for the learner however long they take: the story follows progress, not the calendar."""
    latest = (
        await db.execute(
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.city == city,
                Session.kind == kind,
                Session.ended_at.is_(None),
                Session.plan["status"].as_string().in_(("planning", "ready")),
            )
            .order_by(Session.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return None
    if latest.plan.get("status") == "planning":
        # A plan that has been "planning" this long was lost (worker restart); plan afresh.
        fresh = latest.started_at > datetime.now(UTC) - timedelta(minutes=state.settings.plan_reuse_minutes)
        return latest if fresh else None
    played = (
        await db.execute(select(Scene.id).where(Scene.session_id == latest.id, Scene.status != "planned").limit(1))
    ).scalar_one_or_none()
    return None if played else latest


async def _plan_day(db: Db, state: State, tenant_id: uuid.UUID, user_id: uuid.UUID, city: str, kind: str) -> Session:
    """The day to play next in ``city``: one already planned and unplayed, or a new one queued for planning."""
    if (reusable := await _reusable_day(db, user_id, city, kind, state)) is not None:
        return reusable  # a second tap, a reopened screen, or a day planned ahead: never plan (and pay) twice
    row = Session(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=kind,
        city=city,
        started_at=datetime.now(UTC),
        plan={"status": "planning"},
    )
    db.add(row)
    await db.commit()
    await state.jobs.enqueue(
        GRAPH_JOBS,
        {"kind": "day_planner", "user_id": user_id, "session_id": row.id, "city": city, "trace_id": row.trace_id},
    )
    return row


@router.post("/sessions", response_model=SessionView, status_code=202)
async def start_session(body: StartSessionBody, principal: Principal, state: State, db: Db) -> SessionView:
    require_providers(state, llm=True)
    row = await _plan_day(db, state, principal.tenant_id, principal.user_id, body.city, body.kind)
    return await get_session(row.id, principal, db)


@router.get("/sessions/{session_id}", response_model=SessionView)
async def get_session(session_id: uuid.UUID, principal: Principal, db: Db) -> SessionView:
    row = await _owned_session(db, principal, session_id)
    scenes = (await db.execute(select(Scene.id).where(Scene.session_id == row.id).order_by(Scene.created_at))).scalars()
    plan_status = "ended" if row.ended_at else str(row.plan.get("status", "planning"))
    return SessionView(
        id=row.id,
        city=row.city,
        kind=row.kind,
        status=plan_status,
        scene_ids=list(scenes),
        # Plans saved before incremental planning have no flag and were always whole.
        complete=plan_status in ("ended", "failed") or bool(row.plan.get("complete", plan_status == "ready")),
        notebook=row.plan.get("notebook"),
        error=row.plan.get("error"),
    )


@router.post("/sessions/{session_id}/end", response_model=SessionView)
async def end_session(session_id: uuid.UUID, principal: Principal, state: State, db: Db) -> SessionView:
    row = await _owned_session(db, principal, session_id)
    if row.ended_at is None:
        row.ended_at = datetime.now(UTC)
        await db.commit()
        await state.jobs.enqueue(
            GRAPH_JOBS,
            {
                "kind": "night_consolidation",
                "user_id": principal.user_id,
                "session_id": row.id,
                "trace_id": row.trace_id,
            },
        )
        if row.kind == "live" and row.city and any_llm_configured():
            # The next story day is planned now, after consolidation (jobs run in order), so it is ready when the
            # learner is: finishing a day unlocks the next one, whatever the time.
            await _plan_day(db, state, principal.tenant_id, principal.user_id, row.city, row.kind)
    return await get_session(session_id, principal, db)


@router.get("/scenes/{scene_id}", response_model=SceneView)
async def get_scene(scene_id: uuid.UUID, principal: Principal, state: State, db: Db) -> SceneView:
    row = await db.get(Scene, scene_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such scene")
    view = scene_view(row)
    city = load_city(state.settings.content_root, view.city)
    location = city.location(view.location_key)
    npc = city.npc(view.npc_keys[0]) if view.npc_keys else None
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == principal.user_id))).scalar_one()
    band = profile.settings.get("language_bands", {}).get(CITY_LANGUAGE[view.city])
    return view.model_copy(
        update={
            "location_name": location.name,
            "layer_art": list(location.layer_art),
            "npc_name": npc.name if npc else "",
            "npc_role": npc.role if npc else "",
            "learner_band": int(band) if band is not None else None,
        }
    )


@router.post("/scenes/{scene_id}/live", response_model=LiveTicket)
async def go_live(scene_id: uuid.UUID, principal: Principal, state: State, db: Db) -> LiveTicket:
    row = await db.get(Scene, scene_id)
    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such scene")
    contract = SceneContract.model_validate(row.contract)
    user = await db.get_one(User, principal.user_id)
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == user.id))).scalar_one()
    band = int(profile.settings.get("language_bands", {}).get(CITY_LANGUAGE[contract.city], 5))
    room = f"scene-{row.id.hex}"
    settings = state.settings
    token = mint_learner_token(
        settings.livekit_api_key,
        settings.livekit_api_secret.get_secret_value(),
        room,
        str(principal.user_id),
        user.display_name,
    )
    session = await db.get_one(Session, row.session_id)
    await state.jobs.enqueue(
        LIVE_JOBS,
        {
            "room": room,
            "user_id": principal.user_id,
            "session_id": row.session_id,
            "trace_id": session.trace_id,
            "learner_name": user.display_name,
            "learner_band": band,
            "intra_pauses_ms": profile.settings.get("intra_pauses_ms", []),
            "contract": contract.model_dump(mode="json"),
        },
    )
    row.status = "live"
    await db.commit()
    return LiveTicket(livekit_url=settings.livekit_public_url, room=room, token=token, scene_id=row.id)
