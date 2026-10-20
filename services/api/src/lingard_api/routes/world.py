"""``/v1/world``: renderer-independent world state (SPEC §19.1); the client only renders it."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from lingard_api.deps import Db, Principal, State
from lingard_api.routes.economy import flat_decor
from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, LANGUAGE_SCALE, CityKey
from lingard_contracts.world import CityEntry, WorldView
from lingard_db.models import LearnerProfile, Session, WorldState
from lingard_world import load_city

router = APIRouter(prefix="/v1/world", tags=["world"])


@router.get("", response_model=list[CityEntry])
async def cities(principal: Principal, state: State) -> list[CityEntry]:
    entries = []
    for key, language in CITY_LANGUAGE.items():
        city, pack = load_city(state.settings.content_root, key).city, LANGUAGE_PACK[language]
        name = state.packs.pack(pack).name
        scale = LANGUAGE_SCALE[language]
        entry = CityEntry(
            city=city.key, name=city.name, language=language, pack=pack, pack_name=name, level_scale=scale
        )
        entries.append(entry)
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
    view = content.view(hour=hour if hour is not None else state.settings.world_hour, band=band, extra_unlocks=unlocks)
    decor = await flat_decor(state, principal.user_id)
    districts = [
        d.model_copy(
            update={
                "locations": [
                    loc.model_copy(update={"layer_art": [*loc.layer_art, *decor]}) if loc.kind == "home" else loc
                    for loc in d.locations
                ]
            }
        )
        for d in view.districts
    ]
    return view.model_copy(update={"districts": districts, "days_lived": await days_lived(db, principal.user_id, city)})


async def days_lived(db: Db, user_id: object, city: str) -> int:
    """Finished story days in a city: the learner's progress there, independent of the calendar."""
    finished = (
        select(func.count())
        .select_from(Session)
        .where(Session.user_id == user_id, Session.city == city, Session.kind == "live", Session.ended_at.is_not(None))
    )
    return int((await db.execute(finished)).scalar_one())
