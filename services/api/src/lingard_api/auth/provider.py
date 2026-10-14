"""``AuthProvider`` interface (SPEC §23.2): PIN today; magic links, passkeys or OAuth later behind the same seam."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SignInRequest:
    display_name: str
    secret: str
    device_label: str
    ip: str | None = None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    session_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    pin_change_required: bool


class AuthError(Exception):
    """Generic failure. The message never reveals whether a name exists."""

    def __init__(self, message: str = "Invalid name or PIN", *, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


class AuthProvider(Protocol):
    async def sign_in(self, request: SignInRequest) -> TokenPair: ...

    async def refresh(self, refresh_token: str, ip: str | None = None) -> TokenPair: ...

    async def sign_out(self, session_id: uuid.UUID) -> None: ...
