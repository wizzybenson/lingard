"""FastAPI dependencies: app state, DB session, and the authenticated principal."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.auth.tokens import AccessClaims, TokenError
from lingard_api.state import AppState

bearer = HTTPBearer(auto_error=False)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.lingard
    return state


State = Annotated[AppState, Depends(get_state)]


async def get_db(state: State) -> AsyncIterator[AsyncSession]:
    async with state.sessions() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _claims(
    state: State, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> AccessClaims:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = state.auth.tokens.verify(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from exc
    if await state.auth.active_session(claims.session_id) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    return claims


async def pin_change_allowed(claims: Annotated[AccessClaims, Depends(_claims)]) -> AccessClaims:
    """Authenticated, even if a PIN change is pending (only the change-PIN route uses this)."""
    return claims


async def current_user(claims: Annotated[AccessClaims, Depends(_claims)]) -> AccessClaims:
    if claims.pin_change_required:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PIN change required")
    return claims


async def current_admin(claims: Annotated[AccessClaims, Depends(current_user)]) -> AccessClaims:
    if claims.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return claims


Principal = Annotated[AccessClaims, Depends(current_user)]
Admin = Annotated[AccessClaims, Depends(current_admin)]
PendingPrincipal = Annotated[AccessClaims, Depends(pin_change_allowed)]
