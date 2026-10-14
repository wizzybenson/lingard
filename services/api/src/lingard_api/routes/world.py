"""``/v1/world``: renderer-independent world state (SPEC §19.1); the client only renders it."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from lingard_api.deps import Db, Principal, State
from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, CityKey
from lingard_contracts.world import CityEntry, WorldView
from lingard_db.models import LearnerProfile, WorldState
from lingard_world import load_city

router = APIRouter(prefix="/v1/world", tags=["world"])


@router.get("", response_model=list[CityEntry])
async def cities(principal: Principal, state: State) -> list[CityEntry]:
    entries = []
    for key, language in CITY_LANGUAGE.items():
        city, pack = load_city(state.settings.content_root, key).city, LANGUAGE_PACK[language]
        name = state.packs.pack(pack).name
        entries.append(CityEntry(city=city.key, name=city.name, language=language, pack=pack, pack_name=name))
    return entries


@router.get("/{city}", response_model=WorldView)
async def get_world(city: CityKey, principal: Principal, state: State, db: Db, hour: int | None = None) -> WorldView:
    if hour is not None and not 0 <= hour <= 23:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "hour must be 0–23")
    content = load_city(state.settings.content_root, city)
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == principal.user_id))).scalar_one()
    band = int(profile.settings.get("language_bands", {}).get(CITY_LANGUAGE[city], 1))
    world = (
        await db.execute(select(WorldState).where(WorldState.user_id == principal.user_id, WorldState.city == city))
    ).scalar_one_or_none()
    unlocks = list(world.district_unlocks) if world else []
    return content.view(hour=hour if hour is not None else datetime.now().hour, band=band, extra_unlocks=unlocks)
