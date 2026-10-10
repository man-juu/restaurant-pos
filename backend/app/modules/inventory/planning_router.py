"""Producible quantity (FR-INV-020) and demand forecast (FR-INV-018) per outlet. Outlet scope
on every call."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import item_names, stock_items, tenant_today
from app.modules.inventory import forecast as forecasting
from app.modules.inventory import permissions as perm
from app.modules.inventory import planning
from app.modules.inventory.levels import on_hand_by_item
from app.modules.inventory.schemas import ForecastRow, ProducibleRow

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


@router.get("/producible", response_model=list[ProducibleRow])
async def producible(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[ProducibleRow]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rows = await planning.producible(db, outlet_id, await tenant_today(db, p.tenant_id))
        ids = {r.item_id for r in rows} | {r.limiting_item_id for r in rows if r.limiting_item_id}
        names = await item_names(db, p.tenant_id, lang, ids)
    out = [
        ProducibleRow(
            item_id=r.item_id,
            name=names[r.item_id].name,
            unit_code=names[r.item_id].unit_code,
            can_make=r.can_make,
            limiting_item_id=r.limiting_item_id,
            limiting_name=names[r.limiting_item_id].name if r.limiting_item_id else None,
        )
        for r in rows
    ]
    return sorted(out, key=lambda r: (r.can_make, r.name.lower()))


@router.get("/forecast", response_model=list[ForecastRow])
async def forecast(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    days: Annotated[int, Query(ge=1, le=28)] = 7,
    lang: Lang = "en",
) -> list[ForecastRow]:
    """FR-INV-018: items used here in the last weeks, with what they should need next."""
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        today = await tenant_today(db, p.tenant_id)
        ids = await forecasting.used_items(db, outlet_id, today)
        ahead = await forecasting.forecasts(db, outlet_id, ids, today)
        conf = await forecasting.planning_settings(db, outlet_id)
        costs = await forecasting.unit_costs(db, outlet_id, ids)
        items = await stock_items(db, ids)
        have = await on_hand_by_item(db, outlet_id, ids)
        names = await item_names(db, p.tenant_id, lang, ids)
    rows = [
        ForecastRow(
            item_id=f.item_id,
            name=names[f.item_id].name,
            unit_code=names[f.item_id].unit_code,
            enough_history=f.enough_history,
            trend=f.trend,
            daily=f.daily,
            days=f.days(today + timedelta(days=1), days),
            on_hand=have.get(f.item_id, Decimal(0)),
            eoq=forecasting.eoq(
                f.daily, costs.get(f.item_id), conf, items[f.item_id].shelf_life_days
            ),
        )
        for f in ahead.values()
        if f.item_id in names and f.item_id in items and f.daily > 0
    ]
    return sorted(rows, key=lambda r: r.name.lower())
