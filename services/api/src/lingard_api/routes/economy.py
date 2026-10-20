"""``/v1``: wallet, shop, Draw Day and the friends league (SPEC §18). Nothing purchasable skips learning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from lingard_api.deps import Db, Principal, State
from lingard_api.state import AppState
from lingard_contracts.common import CITY_LANGUAGE
from lingard_db.models import Draw, LearnerProfile, Ledger, Scene, Session, SimCrsSnapshot, User, Wallet
from lingard_economy.crs import DISCLAIMER
from lingard_economy.events import draw_day, league
from lingard_economy.rewards import HOLD, SHOP, LedgerEntry
from lingard_graphs.streaks import learner_streak
from lingard_world import load_city

router = APIRouter(prefix="/v1", tags=["economy"])

GIFT_WARMTH = 0.2
"""How much warmer a character feels after a gift (relationships run from -1 to 1)."""


class ShopItem(BaseModel):
    key: str
    price: int
    held: int
    """How many the learner holds now: spare freezes, flat upgrades bought; 0 for items used at once."""
    limit: int | None
    """The most a learner can hold, if there is a limit."""


class WalletView(BaseModel):
    coins: int
    stars_total: int
    recent: list[dict[str, Any]]
    items: list[ShopItem]


class Friend(BaseModel):
    """A character the learner has met in the story, who can be given a gift."""

    npc_key: str
    name: str
    role: str
    warmth: float
    gifted_today: bool


class BuyBody(BaseModel):
    city: str | None = None
    """Where a café visit or a gift happens."""
    npc_key: str | None = None
    """Who receives a gift."""


FLAT_DECOR = [f"decor/flat_{level}.svg" for level in range(1, HOLD["flat_upgrade"] + 1)]
"""The art each flat upgrade adds to the learner's home, drawn over the home's own layers."""


async def flat_decor(state: AppState, user_id: uuid.UUID) -> list[str]:
    """Décor layers for the learner's home: one more for each flat upgrade bought."""
    return FLAT_DECOR[: len(await state.graph_deps.store.ledger_refs(user_id, "shop:flat_upgrade"))]


async def _held(state: AppState, user_id: uuid.UUID) -> dict[str, int]:
    _, freezes = await learner_streak(state.graph_deps.store, user_id, datetime.now(UTC).date())
    flat = len(await state.graph_deps.store.ledger_refs(user_id, "shop:flat_upgrade"))
    return {"streak_freeze": freezes, "flat_upgrade": flat}


@router.get("/wallet", response_model=WalletView)
async def wallet(principal: Principal, state: State, db: Db) -> WalletView:
    row = (await db.execute(select(Wallet).where(Wallet.user_id == principal.user_id))).scalar_one()
    entries = await db.execute(
        select(Ledger)
        .where(Ledger.user_id == principal.user_id, Ledger.delta != 0)
        .order_by(Ledger.created_at.desc())
        .limit(20)
    )
    held = await _held(state, principal.user_id)
    return WalletView(
        coins=row.coins,
        stars_total=row.stars_total,
        items=[ShopItem(key=k, price=p, held=held.get(k, 0), limit=HOLD.get(k)) for k, p in SHOP.items()],
        recent=[
            {"currency": e.currency, "delta": e.delta, "reason": e.reason, "at": e.created_at}
            for e in entries.scalars()
        ],
    )


async def _met(db: Db, user_id: uuid.UUID, city: str) -> list[str]:
    """Characters the learner has spoken with in this city, most recent first."""
    rows = await db.execute(
        select(Scene.contract["cast"][0]["npc_key"].astext)
        .join(Session, Session.id == Scene.session_id)
        .where(Scene.user_id == user_id, Scene.status != "planned", Session.kind == "live", Session.city == city)
        .order_by(Scene.updated_at.desc())
    )
    return list(dict.fromkeys(k for k in rows.scalars() if k))


@router.get("/shop/friends", response_model=list[Friend])
async def friends(city: str, principal: Principal, state: State, db: Db) -> list[Friend]:
    content = load_city(state.settings.content_root, city)
    today = datetime.now(UTC).date().isoformat()
    gifted = set(await state.graph_deps.store.ledger_refs(principal.user_id, "shop:npc_gift"))
    out = []
    for key in await _met(db, principal.user_id, city):
        if key not in content.npcs:
            continue
        npc = content.npc(key)
        warmth, _ = await state.graph_deps.store.relationship(principal.user_id, key)
        out.append(
            Friend(npc_key=key, name=npc.name, role=npc.role, warmth=warmth, gifted_today=f"{key}:{today}" in gifted)
        )
    return out


@router.post("/shop/{item}", response_model=WalletView)
async def buy(item: str, principal: Principal, state: State, db: Db, body: BuyBody | None = None) -> WalletView:
    """Pay for an item and give it its effect (decision 0023). Checks come first, so a refused purchase costs
    nothing."""
    if item not in SHOP:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")
    store, body = state.graph_deps.store, body or BuyBody()
    user, today = principal.user_id, datetime.now(UTC).date().isoformat()
    held = await _held(state, user)
    if item in HOLD and held.get(item, 0) >= HOLD[item]:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have as many as you can hold")
    ref, key = str(uuid.uuid4()), None
    place, npc_key = body.city or "", body.npc_key or ""
    if item in ("cafe_visit", "npc_gift"):
        if place not in CITY_LANGUAGE:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Which city?")
        city = load_city(state.settings.content_root, place)
        world = await store.world_state(user, place)
    if item == "cafe_visit":
        band = (await store.profile(user)).language_bands.get(CITY_LANGUAGE[place], 4)
        settings = city.story_settings(band, world.get("district_unlocks", []))
        if not any(city.location(loc).kind == "cafe" for loc, _ in settings):
            raise HTTPException(status.HTTP_409_CONFLICT, "No café is open to you yet")
        ref = f"{place}:{ref}"
    if item == "npc_gift":
        if npc_key not in await _met(db, user, place):
            raise HTTPException(status.HTTP_409_CONFLICT, "Meet them in the story first")
        ref = key = f"{npc_key}:{today}"  # one gift per character a day
    entry = LedgerEntry("coins", -SHOP[item], f"shop:{item}", ref, f"spend:{item}:{key or ref}")
    try:
        if not await store.apply_ledger(user, [entry]):
            raise HTTPException(status.HTTP_409_CONFLICT, "Already given today")
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough coins") from exc
    if item == "cafe_visit":  # held until the next story day, which adds a mission at the café (day planner)
        await store.save_world_state(user, place, {**world, "inventory": [*world.get("inventory", []), item]})
    if item == "npc_gift":  # they warm to the learner, and the story remembers it
        npc = city.npc(npc_key)
        warmth, summary = await store.relationship(user, npc_key)
        await store.save_relationship(user, npc_key, min(1.0, warmth + GIFT_WARMTH), summary)
        flags = {**world.get("story_flags", {}), f"gift_{npc_key}": f"The learner gave {npc.name} a small gift."}
        await store.save_world_state(user, place, {**world, "story_flags": flags})
    return await wallet(principal, state, db)


@router.get("/draws/latest")
async def latest_draw(principal: Principal, db: Db) -> dict[str, Any]:
    draw = (await db.execute(select(Draw).order_by(Draw.held_at.desc()).limit(1))).scalar_one_or_none()
    snapshot = (
        await db.execute(
            select(SimCrsSnapshot.value)
            .where(SimCrsSnapshot.user_id == principal.user_id)
            .order_by(SimCrsSnapshot.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if draw is None:
        return {"draw": None, "disclaimer": DISCLAIMER}
    outcome = draw_day(snapshot or 0, draw.cutoff)
    return {
        "draw": {"held_at": draw.held_at, "cutoff": draw.cutoff, "source_note": draw.source_note},
        "sim_crs": snapshot,
        "invited": outcome.invited,
        "margin": outcome.margin,
        "disclaimer": DISCLAIMER,
    }


@router.get("/league")
async def friends_league(principal: Principal, db: Db) -> dict[str, Any]:
    """Weekly ranking by simulated-CRS gain among learners who opted in (consents.friends_league)."""
    week_ago = datetime.now(UTC) - timedelta(days=7)
    profiles = (await db.execute(select(LearnerProfile))).scalars().all()
    opted = {str(p.user_id) for p in profiles if (p.consents or {}).get("friends_league")}
    if str(principal.user_id) not in opted:
        return {"opted_in": False, "ranking": []}
    gains: dict[str, int] = {}
    for user_id in opted:
        latest = (
            await db.execute(select(func.max(SimCrsSnapshot.value)).where(SimCrsSnapshot.user_id == uuid.UUID(user_id)))
        ).scalar_one_or_none() or 0
        before = (
            await db.execute(
                select(SimCrsSnapshot.value)
                .where(SimCrsSnapshot.user_id == uuid.UUID(user_id), SimCrsSnapshot.computed_at < week_ago)
                .order_by(SimCrsSnapshot.computed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none() or latest
        gains[user_id] = latest - before
    names = {
        str(u.id): u.display_name
        for u in (await db.execute(select(User).where(User.id.in_([uuid.UUID(u) for u in opted])))).scalars()
    }
    return {"opted_in": True, "ranking": [{"name": names.get(u, "?"), "gain": g} for u, g in league(gains, opted)]}
