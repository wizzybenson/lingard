"""``/v1``: wallet, shop, Draw Day and the friends league (SPEC §18). Nothing purchasable skips learning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from lingard_api.deps import Db, Principal, State
from lingard_db.models import Draw, LearnerProfile, Ledger, SimCrsSnapshot, User, Wallet
from lingard_economy.crs import DISCLAIMER
from lingard_economy.events import draw_day, league
from lingard_economy.rewards import SHOP, LedgerEntry

router = APIRouter(prefix="/v1", tags=["economy"])


class WalletView(BaseModel):
    coins: int
    stars_total: int
    recent: list[dict[str, Any]]
    shop: dict[str, int]


@router.get("/wallet", response_model=WalletView)
async def wallet(principal: Principal, db: Db) -> WalletView:
    row = (await db.execute(select(Wallet).where(Wallet.user_id == principal.user_id))).scalar_one()
    entries = await db.execute(
        select(Ledger).where(Ledger.user_id == principal.user_id).order_by(Ledger.created_at.desc()).limit(20)
    )
    return WalletView(
        coins=row.coins,
        stars_total=row.stars_total,
        shop=SHOP,
        recent=[
            {"currency": e.currency, "delta": e.delta, "reason": e.reason, "at": e.created_at}
            for e in entries.scalars()
        ],
    )


@router.post("/shop/{item}", response_model=WalletView)
async def buy(item: str, principal: Principal, state: State, db: Db) -> WalletView:
    if item not in SHOP:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")
    entry = LedgerEntry("coins", -SHOP[item], f"shop:{item}", item, f"spend:{item}:{uuid.uuid4()}")
    try:
        await state.graph_deps.store.apply_ledger(principal.user_id, [entry])
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough coins") from exc
    return await wallet(principal, db)


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
