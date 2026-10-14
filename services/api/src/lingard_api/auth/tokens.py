"""Short-lived access JWTs and opaque rotating refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    session_id: uuid.UUID
    role: str
    pin_change_required: bool


class TokenError(Exception):
    pass


class AccessTokens:
    def __init__(self, secret: str, issuer: str, minutes: int) -> None:
        self._secret = secret
        self._issuer = issuer
        self._ttl = timedelta(minutes=minutes)

    def issue(self, claims: AccessClaims, now: datetime | None = None) -> tuple[str, datetime]:
        issued = now or datetime.now(UTC)
        expires = issued + self._ttl
        payload = {
            "sub": str(claims.user_id),
            "tid": str(claims.tenant_id),
            "sid": str(claims.session_id),
            "role": claims.role,
            "pcr": claims.pin_change_required,
            "iss": self._issuer,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm="HS256"), expires

    def verify(self, token: str) -> AccessClaims:
        try:
            data = jwt.decode(token, self._secret, algorithms=["HS256"], issuer=self._issuer)
            return AccessClaims(
                user_id=uuid.UUID(data["sub"]),
                tenant_id=uuid.UUID(data["tid"]),
                session_id=uuid.UUID(data["sid"]),
                role=str(data["role"]),
                pin_change_required=bool(data.get("pcr", False)),
            )
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise TokenError("invalid access token") from exc
