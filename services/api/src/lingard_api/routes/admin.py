"""``/v1/admin``: users, invites, PIN resets, sessions, curriculum review, draws, audit (founder only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from lingard_api import audit
from lingard_api.auth.provider import AuthError
from lingard_api.deps import Admin, Db, State
from lingard_contracts.common import Language
from lingard_curriculum.models import CurriculumNode, NodeKind
from lingard_db.models import AuditLog, Draw, User

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class CreateUserBody(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)
    role: Literal["learner", "admin"] = "learner"


class OneTimePin(BaseModel):
    user_id: uuid.UUID
    one_time_pin: str
    note: str = "Share privately. It must be changed at first sign-in."


class InviteBody(BaseModel):
    role: Literal["learner", "admin"] = "learner"


class InviteView(BaseModel):
    code: str
    expires_at: datetime


class UserView(BaseModel):
    id: uuid.UUID
    display_name: str
    role: str
    locked: bool
    requires_admin_reset: bool
    must_change_pin: bool
    created_at: datetime


class DrawBody(BaseModel):
    category: str = Field("french", max_length=32, description="A category key from content/crs/draws.yaml")
    held_at: datetime
    cutoff: int = Field(ge=0, le=1200)
    source_note: str = Field(min_length=5, description="Where the real cutoff came from (IRCC round page, date)")


class DrawView(DrawBody):
    id: uuid.UUID


class AuditView(BaseModel):
    action: str
    actor_id: uuid.UUID | None
    target: str | None
    at: datetime


def _http(exc: AuthError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("/users", response_model=list[UserView])
async def list_users(admin: Admin, db: Db) -> list[UserView]:
    rows = await db.execute(
        select(User).where(User.tenant_id == admin.tenant_id, User.deleted_at.is_(None)).order_by(User.created_at)
    )
    now = datetime.now().astimezone()
    return [
        UserView(
            id=u.id,
            display_name=u.display_name,
            role=u.role,
            locked=u.locked_until is not None and u.locked_until > now,
            requires_admin_reset=u.requires_admin_reset,
            must_change_pin=u.must_change_pin,
            created_at=u.created_at,
        )
        for u in rows.scalars()
    ]


@router.post("/users", response_model=OneTimePin, status_code=201)
async def create_user(body: CreateUserBody, admin: Admin, state: State) -> OneTimePin:
    try:
        user_id, pin = await state.auth.create_user(admin, body.display_name, body.role)
    except AuthError as exc:
        raise _http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return OneTimePin(user_id=user_id, one_time_pin=pin)


@router.post("/invites", response_model=InviteView, status_code=201)
async def create_invite(body: InviteBody, admin: Admin, state: State) -> InviteView:
    code, expires = await state.auth.create_invite(admin, body.role)
    return InviteView(code=code, expires_at=expires)


@router.post("/users/{user_id}/reset-pin", response_model=OneTimePin)
async def reset_pin(user_id: uuid.UUID, admin: Admin, state: State) -> OneTimePin:
    try:
        return OneTimePin(user_id=user_id, one_time_pin=await state.auth.admin_reset_pin(admin, user_id))
    except AuthError as exc:
        raise _http(exc) from exc


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_all(user_id: uuid.UUID, admin: Admin, state: State) -> dict[str, int]:
    return {"revoked": await state.auth.revoke_all(admin, user_id)}


@router.get("/curriculum", response_model=list[CurriculumNode])
async def curriculum(
    admin: Admin, state: State, language: Language, kind: NodeKind | None = None, band: int | None = None
) -> list[CurriculumNode]:
    return await state.curriculum.nodes(language, kinds=[kind] if kind else (), band=band, reviewed_only=False)


@router.post("/curriculum/{key}/review", response_model=CurriculumNode)
async def review_node(key: str, admin: Admin, state: State, db: Db, reviewed: bool = True) -> CurriculumNode:
    try:
        node = (
            await state.curriculum.mark_reviewed(key, f"user:{admin.user_id}")
            if reviewed
            else await state.curriculum.unmark_reviewed(key)
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such node") from exc
    audit.record(db, "curriculum_reviewed" if reviewed else "curriculum_unreviewed", actor_id=admin.user_id, target=key)
    await db.commit()
    return node


@router.get("/draws", response_model=list[DrawView])
async def list_draws(admin: Admin, db: Db) -> list[DrawView]:
    rows = await db.execute(select(Draw).order_by(Draw.held_at.desc()))
    return [
        DrawView(id=d.id, category=d.category, held_at=d.held_at, cutoff=d.cutoff, source_note=d.source_note)
        for d in rows.scalars()
    ]


@router.post("/draws", response_model=DrawView, status_code=201)
async def add_draw(body: DrawBody, admin: Admin, db: Db) -> DrawView:
    draw = Draw(category=body.category, held_at=body.held_at, cutoff=body.cutoff, source_note=body.source_note)
    db.add(draw)
    audit.record(db, "draw_added", actor_id=admin.user_id, target=str(body.cutoff))
    await db.commit()
    return DrawView(id=draw.id, **body.model_dump())


@router.get("/audit", response_model=list[AuditView])
async def audit_log(admin: Admin, db: Db, limit: int = 200) -> list[AuditView]:
    rows = await db.execute(select(AuditLog).order_by(AuditLog.at.desc()).limit(min(limit, 1000)))
    return [AuditView(action=a.action, actor_id=a.actor_id, target=a.target, at=a.at) for a in rows.scalars()]
