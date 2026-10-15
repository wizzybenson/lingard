"""``/v1/auth``: sign-in, invite redemption, refresh, sign-out, PIN change, device sessions.

Phones keep the refresh token in the OS keychain. Browsers have no equivalent that page scripts can't read, so a client
sending ``X-Lingard-Client: web`` gets the refresh token as an ``HttpOnly`` cookie instead of in the body. Cookie
refreshes require that header too: a cross-site page can only add it after a CORS preflight, which the origin allowlist
refuses, and ``SameSite=Strict`` keeps other sites from sending the cookie at all (decision 0008).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from lingard_api.auth.pin import WeakPinError
from lingard_api.auth.provider import AuthError, SignInRequest, TokenPair
from lingard_api.deps import Db, PendingPrincipal, Principal, State, client_ip
from lingard_api.state import AppState
from lingard_db.models import DeviceSession

router = APIRouter(prefix="/v1/auth", tags=["auth"])

REFRESH_COOKIE = "lingard_refresh"
WEB_CLIENT = "web"

Pin = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SignInBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    pin: str = Pin
    device_label: str = Field(default="device", max_length=120)


class RedeemBody(SignInBody):
    invite_code: str = Field(min_length=4, max_length=32)


class RefreshBody(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=200)
    """Phones send it here; the web sends nothing and relies on the cookie."""


class ChangePinBody(BaseModel):
    current_pin: str = Pin
    new_pin: str = Pin


class TokenResponse(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str | None
    """``None`` for web clients, which receive it as an HttpOnly cookie."""
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


ClientKind = Annotated[str | None, Header(alias="X-Lingard-Client")]


def _issue(pair: TokenPair, client: str | None, response: Response, state: AppState) -> TokenResponse:
    """Phones get the refresh token in the body; the web gets it as a cookie its scripts can't read."""
    body = TokenResponse.of(pair)
    if client != WEB_CLIENT:
        return body
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        max_age=state.settings.refresh_token_days * 86_400,
        path=router.prefix,
        secure=state.settings.refresh_cookie_is_secure,
        httponly=True,
        samesite="strict",
    )
    return body.model_copy(update={"refresh_token": None})


def _forget(response: Response, state: AppState) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=router.prefix,
        secure=state.settings.refresh_cookie_is_secure,
        httponly=True,
        samesite="strict",
    )


def _fail(exc: AuthError | WeakPinError | ValueError) -> HTTPException:
    if isinstance(exc, AuthError):
        return HTTPException(exc.status, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.post("/sign-in", response_model=TokenResponse)
async def sign_in(
    body: SignInBody, request: Request, response: Response, state: State, client: ClientKind = None
) -> TokenResponse:
    try:
        pair = await state.auth.sign_in(
            SignInRequest(body.display_name, body.pin, body.device_label, client_ip(request))
        )
    except AuthError as exc:
        raise _fail(exc) from exc
    return _issue(pair, client, response, state)


@router.post("/redeem-invite", response_model=TokenResponse, status_code=201)
async def redeem_invite(
    body: RedeemBody, request: Request, response: Response, state: State, client: ClientKind = None
) -> TokenResponse:
    try:
        pair = await state.auth.redeem_invite(
            body.invite_code, body.display_name, body.pin, body.device_label, client_ip(request)
        )
    except (AuthError, WeakPinError, ValueError) as exc:
        raise _fail(exc) from exc
    return _issue(pair, client, response, state)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    state: State,
    body: RefreshBody | None = None,
    client: ClientKind = None,
    cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse | JSONResponse:
    token = body.refresh_token if body else None
    if token is None and client == WEB_CLIENT:
        token = cookie
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        pair = await state.auth.refresh(token, client_ip(request))
    except AuthError as exc:
        if client != WEB_CLIENT:
            raise _fail(exc) from exc
        failed = JSONResponse({"detail": str(exc)}, status_code=exc.status)
        _forget(failed, state)  # a dead cookie would only fail again on the next reload
        return failed
    return _issue(pair, client, response, state)


@router.post("/sign-out", status_code=204)
async def sign_out(principal: PendingPrincipal, response: Response, state: State) -> None:
    await state.auth.sign_out(principal.session_id)
    _forget(response, state)


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
