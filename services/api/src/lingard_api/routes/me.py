"""``/v1/me``: the learner's own profile, targets, consents and CRS inputs."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from lingard_api import audit
from lingard_api.deps import Db, Principal
from lingard_contracts.common import PackId, Skill
from lingard_db.models import LearnerProfile, User

router = APIRouter(prefix="/v1/me", tags=["me"])

DEFAULT_TARGETS = {
    "ielts_gt": {"listening": 10, "reading": 10, "writing": 10, "speaking": 10},
    "tef_canada": {"listening": 7, "reading": 7, "writing": 7, "speaking": 7},
}
"""SPEC §26 defaults, as CLB/NCLC levels: CLB 10 in English, NCLC 7 minimum in French."""


class Consents(BaseModel):
    voice_clone: bool = False
    audio_retention_extended: bool = False
    friends_league: bool = False


class ProfileView(BaseModel):
    display_name: str
    role: str
    ui_locale: Literal["en", "fr", "ar"] | None
    """None until the learner chooses; the app then shows the device language and saves it."""
    target_bands: dict[str, dict[str, int]]
    crs_inputs: dict[str, Any]
    model_accent: dict[str, str]
    consents: Consents
    intensity_cap: Literal["calm", "tense", "heated"]
    l1: str
    language_bands: dict[str, int] = {}
    exam_dates: dict[str, date | None] = {}
    """The exams the learner is preparing for, each with its date when known."""


class ProfileUpdate(BaseModel):
    ui_locale: Literal["en", "fr", "ar"] | None = None
    target_bands: dict[PackId, dict[Skill, Annotated[int, Field(ge=4, le=10)]]] | None = None
    """CLB/NCLC level the learner needs per skill (4–10, the range the official conversion tables cover)."""
    exam_dates: dict[PackId, date | Literal[""] | None] | None = None
    """Booked or planned exam date per pack; "" prepares for it without a date yet; null stops preparing for it."""
    crs_inputs: dict[str, Any] | None = None
    model_accent: dict[str, str] | None = None
    consents: Consents | None = None
    intensity_cap: Literal["calm", "tense", "heated"] | None = None
    l1: str | None = Field(default=None, max_length=8)


async def _load(db: Db, principal: Principal) -> tuple[User, LearnerProfile]:
    user = await db.get_one(User, principal.user_id)
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == user.id))).scalar_one()
    return user, profile


def _view(user: User, profile: LearnerProfile) -> ProfileView:
    return ProfileView(
        display_name=user.display_name,
        role=user.role,
        ui_locale=user.ui_locale,
        target_bands=profile.target_bands or DEFAULT_TARGETS,
        crs_inputs=profile.crs_inputs,
        model_accent=profile.model_accent or {"en": "en-GB", "fr": "fr-FR"},
        consents=Consents.model_validate(profile.consents or {}),
        intensity_cap=profile.intensity_cap,
        l1=profile.l1,
        language_bands=dict(profile.settings.get("language_bands", {})),
        exam_dates={k: date.fromisoformat(v) if v else None for k, v in profile.settings.get("exam_dates", {}).items()},
    )


@router.get("", response_model=ProfileView)
async def get_profile(principal: Principal, db: Db) -> ProfileView:
    return _view(*await _load(db, principal))


@router.patch("", response_model=ProfileView)
async def update_profile(body: ProfileUpdate, principal: Principal, db: Db) -> ProfileView:
    user, profile = await _load(db, principal)
    if body.ui_locale:
        user.ui_locale = body.ui_locale
    if body.target_bands is not None:
        merged = {**(profile.target_bands or DEFAULT_TARGETS)}
        for pack_id, skills in body.target_bands.items():
            merged[pack_id] = {**merged.get(pack_id, {}), **{skill.value: level for skill, level in skills.items()}}
        profile.target_bands = merged
    if body.exam_dates is not None:
        dates = dict(profile.settings.get("exam_dates", {}))
        for pack_id, day in body.exam_dates.items():
            if day is None:
                dates.pop(pack_id, None)
            else:
                dates[pack_id] = day.isoformat() if day else ""  # preparing, date not known yet
        profile.settings = {**profile.settings, "exam_dates": dates}
    if body.crs_inputs is not None:
        profile.crs_inputs = body.crs_inputs
    if body.model_accent is not None:
        profile.model_accent = body.model_accent
    if body.intensity_cap:
        profile.intensity_cap = body.intensity_cap
    if body.l1:
        profile.l1 = body.l1
    if body.consents is not None:
        previous = Consents.model_validate(profile.consents or {})
        profile.consents = body.consents.model_dump()
        if previous != body.consents:
            audit.record(
                db, "consents_changed", actor_id=user.id, tenant_id=user.tenant_id, detail=body.consents.model_dump()
            )
    await db.commit()
    return _view(user, profile)
