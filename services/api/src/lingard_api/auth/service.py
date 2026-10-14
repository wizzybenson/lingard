"""Name + PIN authentication with lockout, rate limits and rotating device-bound refresh tokens (SPEC §23.2)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lingard_api import audit
from lingard_api.auth.pin import PinHasher, ensure_strong, generate_pin, normalise_name, validate_display_name
from lingard_api.auth.provider import AuthError, SignInRequest, TokenPair
from lingard_api.auth.ratelimit import RateLimiter
from lingard_api.auth.tokens import AccessClaims, AccessTokens, hash_token, new_refresh_token
from lingard_api.settings import Settings
from lingard_db.models import DeviceSession, Invite, LearnerProfile, Tenant, User, Wallet

GENERIC_FAILURE = "Invalid name or PIN. After several failed attempts, sign-in pauses for a while."
DEFAULT_TENANT = "default"


def _now() -> datetime:
    return datetime.now(UTC)


class PinAuthService:
    """Implements ``AuthProvider`` and the account operations that go with PINs."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        hasher: PinHasher,
        limiter: RateLimiter,
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._hasher = hasher
        self._limiter = limiter
        self._tokens = AccessTokens(
            settings.jwt_secret.get_secret_value(), settings.jwt_issuer, settings.access_token_minutes
        )

    @property
    def tokens(self) -> AccessTokens:
        return self._tokens

    async def verify_pin(self, user_id: uuid.UUID, pin: str) -> bool:
        """Re-authentication for destructive actions (account deletion)."""
        async with self._sessions() as db:
            user = await db.get_one(User, user_id)
        return self._hasher.verify(user.pin_hash, pin)

    async def default_tenant(self, db: AsyncSession) -> Tenant:
        tenant = (await db.execute(select(Tenant).where(Tenant.name == DEFAULT_TENANT))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name=DEFAULT_TENANT)
            db.add(tenant)
            await db.flush()
        return tenant

    async def _user_by_name(self, db: AsyncSession, tenant_id: uuid.UUID, display_name: str) -> User | None:
        return (
            await db.execute(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.name_key == normalise_name(display_name),
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def _new_user(self, db: AsyncSession, tenant: Tenant, display_name: str, pin: str, role: str) -> User:
        name = validate_display_name(display_name)
        if await self._user_by_name(db, tenant.id, name) is not None:
            raise AuthError("That name is taken", status=409)
        user = User(
            tenant_id=tenant.id,
            display_name=name,
            name_key=normalise_name(name),
            pin_hash=self._hasher.hash(pin),
            role=role,
        )
        db.add(user)
        await db.flush()
        db.add(LearnerProfile(tenant_id=tenant.id, user_id=user.id))
        db.add(Wallet(tenant_id=tenant.id, user_id=user.id))
        return user

    # ---- account creation ----------------------------------------------------------------------------------------

    async def bootstrap_admin(self, display_name: str, pin: str) -> uuid.UUID:
        """First admin, from the CLI only. Refuses if any admin already exists."""
        ensure_strong(pin)
        async with self._sessions() as db, db.begin():
            tenant = await self.default_tenant(db)
            exists = (await db.execute(select(User.id).where(User.role == "admin").limit(1))).first()
            if exists:
                raise AuthError("an admin already exists", status=409)
            user = await self._new_user(db, tenant, display_name, pin, "admin")
            audit.record(db, "admin_bootstrapped", actor_id=user.id, tenant_id=tenant.id, target=str(user.id))
            return user.id

    async def create_user(self, admin: AccessClaims, display_name: str, role: str = "learner") -> tuple[uuid.UUID, str]:
        """Admin creates a user and receives a one-time PIN that must be changed at first sign-in."""
        pin = generate_pin()
        async with self._sessions() as db, db.begin():
            tenant = await db.get_one(Tenant, admin.tenant_id)
            user = await self._new_user(db, tenant, display_name, pin, role)
            user.must_change_pin = True
            audit.record(db, "user_created", actor_id=admin.user_id, tenant_id=tenant.id, target=str(user.id))
            return user.id, pin

    async def create_invite(self, admin: AccessClaims, role: str = "learner") -> tuple[str, datetime]:
        code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        expires = _now() + timedelta(days=self._settings.invite_days)
        async with self._sessions() as db, db.begin():
            db.add(
                Invite(
                    tenant_id=admin.tenant_id,
                    code_hash=hash_token(code),
                    created_by=admin.user_id,
                    role=role,
                    expires_at=expires,
                )
            )
            audit.record(db, "invite_created", actor_id=admin.user_id, tenant_id=admin.tenant_id)
        return code, expires

    async def redeem_invite(
        self, code: str, display_name: str, pin: str, device_label: str, ip: str | None
    ) -> TokenPair:
        ensure_strong(pin)
        if not await self._limiter.hit(f"invite-ip:{ip}", self._settings.rate_limit_per_ip_per_minute):
            raise AuthError("Too many attempts. Try again in a minute.", status=429)
        async with self._sessions() as db, db.begin():
            invite = (
                await db.execute(
                    select(Invite).where(Invite.code_hash == hash_token(code.strip().upper())).with_for_update()
                )
            ).scalar_one_or_none()
            if invite is None or invite.used_at is not None or invite.expires_at <= _now():
                raise AuthError("This invite code is not valid", status=400)
            tenant = await db.get_one(Tenant, invite.tenant_id)
            user = await self._new_user(db, tenant, display_name, pin, invite.role)
            invite.used_by, invite.used_at = user.id, _now()
            audit.record(db, "invite_redeemed", actor_id=user.id, tenant_id=tenant.id, target=str(invite.id), ip=ip)
            return await self._open_session(db, user, device_label)

    # ---- sign-in -------------------------------------------------------------------------------------------------

    async def sign_in(self, request: SignInRequest) -> TokenPair:
        settings = self._settings
        name_key = normalise_name(request.display_name)
        ip_ok = await self._limiter.hit(f"signin-ip:{request.ip}", settings.rate_limit_per_ip_per_minute)
        name_ok = await self._limiter.hit(f"signin-name:{name_key}", settings.rate_limit_per_name_per_minute)
        if not (ip_ok and name_ok):
            raise AuthError("Too many attempts. Try again in a minute.", status=429)

        failure = AuthError(GENERIC_FAILURE)
        async with self._sessions() as db, db.begin():
            tenant = await self.default_tenant(db)
            user = await self._user_by_name(db, tenant.id, request.display_name)
            now = _now()
            if user is None:
                self._hasher.burn(request.secret)
                audit.record(
                    db, "signin_failed", tenant_id=tenant.id, target=name_key, ip=request.ip, detail={"r": "u"}
                )
                failure = AuthError(GENERIC_FAILURE)
            elif user.requires_admin_reset or (user.locked_until is not None and user.locked_until > now):
                self._hasher.burn(request.secret)
                audit.record(db, "signin_blocked_locked", actor_id=user.id, tenant_id=tenant.id, ip=request.ip)
                failure = AuthError(GENERIC_FAILURE)
            elif not self._hasher.verify(user.pin_hash, request.secret):
                self._register_failure(db, user, now, request.ip)
                failure = AuthError(GENERIC_FAILURE)
            else:
                user.failed_pin_attempts = 0
                user.lockout_level = 0
                user.locked_until = None
                if self._hasher.needs_rehash(user.pin_hash):
                    user.pin_hash = self._hasher.hash(request.secret)
                audit.record(db, "signin", actor_id=user.id, tenant_id=tenant.id, ip=request.ip)
                return await self._open_session(db, user, request.device_label)
        # Raised after commit: failure counters, lockouts and audit rows must persist.
        raise failure

    def _register_failure(self, db: AsyncSession, user: User, now: datetime, ip: str | None) -> None:
        settings = self._settings
        user.failed_pin_attempts += 1
        audit.record(db, "signin_failed", actor_id=user.id, tenant_id=user.tenant_id, ip=ip, detail={"r": "pin"})
        if user.failed_pin_attempts < settings.lockout_after_failures:
            return
        user.failed_pin_attempts = 0
        user.lockout_level += 1
        if user.lockout_level > len(settings.lockout_minutes):
            user.requires_admin_reset = True
            audit.record(db, "lockout_admin_reset_required", actor_id=user.id, tenant_id=user.tenant_id, ip=ip)
        else:
            minutes = settings.lockout_minutes[user.lockout_level - 1]
            user.locked_until = now + timedelta(minutes=minutes)
            audit.record(db, "lockout", actor_id=user.id, tenant_id=user.tenant_id, ip=ip, detail={"minutes": minutes})

    async def _open_session(self, db: AsyncSession, user: User, device_label: str) -> TokenPair:
        now = _now()
        refresh = new_refresh_token()
        device = DeviceSession(
            tenant_id=user.tenant_id,
            user_id=user.id,
            device_label=device_label[:120] or "device",
            refresh_token_hash=hash_token(refresh),
            pin_verified_at=now,
            expires_at=now + timedelta(days=self._settings.refresh_token_days),
            last_seen_at=now,
        )
        db.add(device)
        await db.flush()
        return self._pair(user, device, refresh)

    def _pair(self, user: User, device: DeviceSession, refresh: str) -> TokenPair:
        claims = AccessClaims(
            user_id=user.id,
            tenant_id=user.tenant_id,
            session_id=device.id,
            role=user.role,
            pin_change_required=user.must_change_pin,
        )
        access, expires = self._tokens.issue(claims)
        return TokenPair(
            access_token=access,
            access_expires_at=expires,
            refresh_token=refresh,
            session_id=device.id,
            user_id=user.id,
            role=user.role,
            pin_change_required=user.must_change_pin,
        )

    # ---- refresh and revocation -----------------------------------------------------------------------------------

    async def refresh(self, refresh_token: str, ip: str | None = None) -> TokenPair:
        token_hash = hash_token(refresh_token)
        expired = AuthError("Session expired. Please sign in again.")
        failure = expired
        async with self._sessions() as db, db.begin():
            device = (
                await db.execute(
                    select(DeviceSession).where(DeviceSession.refresh_token_hash == token_hash).with_for_update()
                )
            ).scalar_one_or_none()
            if device is None:
                reused = (
                    await db.execute(select(DeviceSession).where(DeviceSession.previous_refresh_hash == token_hash))
                ).scalar_one_or_none()
                if reused is not None and reused.revoked_at is None:
                    reused.revoked_at, reused.revoked_reason = _now(), "refresh_reuse"
                    audit.record(db, "session_revoked_reuse", actor_id=reused.user_id, target=str(reused.id), ip=ip)
                failure = expired
            else:
                now = _now()
                user = await db.get_one(User, device.user_id)
                if device.revoked_at is not None or device.expires_at <= now or user.deleted_at is not None:
                    failure = expired
                elif now - device.pin_verified_at > timedelta(days=self._settings.pin_reverify_days):
                    failure = AuthError("Please sign in with your PIN again.")
                else:
                    new_refresh = new_refresh_token()
                    device.previous_refresh_hash = device.refresh_token_hash
                    device.refresh_token_hash = hash_token(new_refresh)
                    device.last_seen_at = now
                    return self._pair(user, device, new_refresh)
        raise failure

    async def sign_out(self, session_id: uuid.UUID) -> None:
        async with self._sessions() as db, db.begin():
            device = await db.get(DeviceSession, session_id)
            if device is not None and device.revoked_at is None:
                device.revoked_at, device.revoked_reason = _now(), "sign_out"
                audit.record(db, "sign_out", actor_id=device.user_id, target=str(session_id))

    async def revoke_session(self, actor: AccessClaims, session_id: uuid.UUID) -> bool:
        async with self._sessions() as db, db.begin():
            device = await db.get(DeviceSession, session_id)
            if device is None or (device.user_id != actor.user_id and actor.role != "admin"):
                return False
            if device.revoked_at is None:
                device.revoked_at, device.revoked_reason = _now(), "revoked"
                audit.record(db, "session_revoked", actor_id=actor.user_id, target=str(session_id))
            return True

    async def revoke_all(self, actor: AccessClaims, user_id: uuid.UUID) -> int:
        if actor.user_id != user_id and actor.role != "admin":
            raise AuthError("Not allowed", status=403)
        async with self._sessions() as db, db.begin():
            result = await db.execute(
                update(DeviceSession)
                .where(DeviceSession.user_id == user_id, DeviceSession.revoked_at.is_(None))
                .values(revoked_at=_now(), revoked_reason="revoke_all")
            )
            audit.record(db, "sessions_revoked_all", actor_id=actor.user_id, target=str(user_id))
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def active_session(self, session_id: uuid.UUID) -> DeviceSession | None:
        async with self._sessions() as db:
            device = await db.get(DeviceSession, session_id)
        if device is None or device.revoked_at is not None or device.expires_at <= _now():
            return None
        return device

    # ---- PIN management -------------------------------------------------------------------------------------------

    async def change_pin(self, claims: AccessClaims, current_pin: str, new_pin: str) -> None:
        ensure_strong(new_pin)
        if current_pin == new_pin:
            raise AuthError("Choose a different PIN", status=400)
        async with self._sessions() as db, db.begin():
            user = await db.get_one(User, claims.user_id)
            wrong = not self._hasher.verify(user.pin_hash, current_pin)
            if wrong:
                self._register_failure(db, user, _now(), None)
        if wrong:
            raise AuthError("Current PIN is wrong", status=400)
        async with self._sessions() as db, db.begin():
            user = await db.get_one(User, claims.user_id)
            user.pin_hash = self._hasher.hash(new_pin)
            user.must_change_pin = False
            await db.execute(
                update(DeviceSession)
                .where(
                    DeviceSession.user_id == user.id,
                    DeviceSession.id != claims.session_id,
                    DeviceSession.revoked_at.is_(None),
                )
                .values(revoked_at=_now(), revoked_reason="pin_changed")
            )
            audit.record(db, "pin_changed", actor_id=user.id, tenant_id=user.tenant_id)

    async def admin_reset_pin(self, admin: AccessClaims, user_id: uuid.UUID) -> str:
        """Issues a one-time PIN, clears lockout, revokes every device, forces a change at next sign-in."""
        pin = generate_pin()
        async with self._sessions() as db, db.begin():
            user = await db.get_one(User, user_id)
            if user.tenant_id != admin.tenant_id:
                raise AuthError("Not found", status=404)
            user.pin_hash = self._hasher.hash(pin)
            user.must_change_pin = True
            user.failed_pin_attempts = 0
            user.lockout_level = 0
            user.locked_until = None
            user.requires_admin_reset = False
            await db.execute(
                update(DeviceSession)
                .where(DeviceSession.user_id == user.id, DeviceSession.revoked_at.is_(None))
                .values(revoked_at=_now(), revoked_reason="admin_reset")
            )
            audit.record(
                db, "pin_reset_by_admin", actor_id=admin.user_id, tenant_id=user.tenant_id, target=str(user.id)
            )
        return pin
