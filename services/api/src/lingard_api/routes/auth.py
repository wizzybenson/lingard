"""``/v1/auth``: sign-in, invite redemption, refresh, sign-out, PIN change, device sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from lingard_api.auth.pin import WeakPinError
from lingard_api.auth.provider import AuthError, SignInRequest, TokenPair
from lingard_api.deps import Db, PendingPrincipal, Principal, State, client_ip
from lingard_db.models import DeviceSession

router = APIRouter(prefix="/v1/auth", tags=["auth"])

Pin = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SignInBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    pin: str = Pin
    device_label: str = Field(default="device", max_length=120)


class RedeemBody(SignInBody):
    invite_code: str = Field(min_length=4, max_length=32)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class ChangePinBody(BaseModel):
    current_pin: str = Pin
    new_pin: str = Pin


class TokenResponse(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    session_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    pin_change_required: bool

    @classmethod
    def of(cls, pair: TokenPair) -> TokenResponse:
        return cls(**pair.__dict__)


class DeviceSessionView(BaseModel):
    id: uuid.UUID
    device_label: str
    last_seen_at: datetime
    current: bool


def _fail(exc: AuthError | WeakPinError | ValueError) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(exc.status, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.post("/sign-in", response_model=TokenResponse)
async def sign_in(body: SignInBody, request: Request, state: State) -> TokenResponse:
    try:
        pair = await state.auth.sign_in(
            SignInRequest(body.display_name, body.pin, body.device_label, client_ip(request))
        )
    except AuthError as exc:
        raise _fail(exc) from exc
    return TokenResponse.of(pair)


@router.post("/redeem-invite", response_model=TokenResponse, status_code=201)
async def redeem_invite(body: RedeemBody, request: Request, state: State) -> TokenResponse:
    try:
        pair = await state.auth.redeem_invite(
            body.invite_code, body.display_name, body.pin, body.device_label, client_ip(request)
        )
    except (AuthError, WeakPinError, ValueError) as exc:
        raise _fail(exc) from exc
    return TokenResponse.of(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshBody, request: Request, state: State) -> TokenResponse:
    try:
        return TokenResponse.of(await state.auth.refresh(body.refresh_token, client_ip(request)))
    except AuthError as exc:
        raise _fail(exc) from exc


@router.post("/sign-out", status_code=204)
async def sign_out(principal: PendingPrincipal, state: State) -> None:
    await state.auth.sign_out(principal.session_id)


@router.post("/change-pin", status_code=204)
async def change_pin(body: ChangePinBody, principal: PendingPrincipal, state: State) -> None:
    try:
        await state.auth.change_pin(principal, body.current_pin, body.new_pin)
    except (AuthError, WeakPinError) as exc:
        raise _fail(exc) from exc


@router.get("/sessions", response_model=list[DeviceSessionView])
async def list_sessions(principal: Principal, db: Db) -> list[DeviceSessionView]:
    rows = await db.execute(
        select(DeviceSession)
        .where(DeviceSession.user_id == principal.user_id, DeviceSession.revoked_at.is_(None))
        .order_by(DeviceSession.last_seen_at.desc())
    )
    return [
        DeviceSessionView(
            id=d.id, device_label=d.device_label, last_seen_at=d.last_seen_at, current=d.id == principal.session_id
        )
        for d in rows.scalars()
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(session_id: uuid.UUID, principal: Principal, state: State) -> None:
    if not await state.auth.revoke_session(principal, session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such session")
