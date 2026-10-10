"""Production plan suggestion (FR-PRD-005): for the next `plan_days` days at a kitchen, what
to make of each item the kitchen produces (semi-finished, with a recipe):

par level + open requests from other outlets due in that time + the outlet's own forecast use
(FR-INV-018) - stock on hand - production already planned in that time, never below 0.

The ingredients on hand may limit it; `can_make` says how much they allow. Accepting the
suggestion creates planned production orders (FR-PRD-001); nothing is made automatically."""

import uuid
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demand import outgoing_demand
from app.core.settings import service as settings
from app.core.settings.schemas import PlanningSettings
from app.modules.catalog.interface import item_names, items_with_recipe, stock_items
from app.modules.inventory.interface import forecasts, par_and_on_hand, producible
from app.modules.production.models import ProductionOrder
from app.modules.production.schemas import PlanRow
from app.modules.production.service import OUTPUT_TYPES

QTY = Decimal("0.0001")


async def _planned(
    db: AsyncSession, outlet_id: uuid.UUID, start: date, end: date
) -> dict[uuid.UUID, Decimal]:
    rows = await db.execute(
        select(ProductionOrder.item_id, func.sum(ProductionOrder.planned_qty))
        .where(
            ProductionOrder.outlet_id == outlet_id,
            ProductionOrder.status == "planned",
            ProductionOrder.production_date >= start,
            ProductionOrder.production_date <= end,
        )
        .group_by(ProductionOrder.item_id)
    )
    return dict(rows.tuples().all())


async def suggestion(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, today: date, language: str
) -> tuple[int, list[PlanRow]]:
    conf = cast(PlanningSettings, await settings.get_setting(db, tenant_id, "planning"))
    end = today + timedelta(days=conf.plan_days)
    made = await items_with_recipe(db, today)
    items = await stock_items(db, made)
    ids = {i for i, it in items.items() if it.type in OUTPUT_TYPES and it.is_active}
    requested = await outgoing_demand(db, tenant_id, outlet_id, end)
    levels = await par_and_on_hand(db, outlet_id, ids)
    ahead = await forecasts(db, outlet_id, ids, today)
    planned = await _planned(db, outlet_id, today, end)
    limits = {p.item_id: p.can_make for p in await producible(db, outlet_id, today)}
    names = await item_names(db, tenant_id, language, ids)
    rows = []
    for item_id in ids:
        par, have = levels.get(item_id, (Decimal(0), Decimal(0)))
        asked = requested.get(item_id, Decimal(0))
        own = sum(ahead[item_id].days(today + timedelta(days=1), conf.plan_days), Decimal(0))
        already = planned.get(item_id, Decimal(0))
        need = (par + asked + own - have - already).quantize(QTY, ROUND_CEILING)
        if need <= 0:
            continue
        rows.append(
            PlanRow(
                item_id=item_id,
                sku=names[item_id].sku,
                name=names[item_id].name,
                unit_code=names[item_id].unit_code,
                par_qty=par,
                on_hand=have,
                requested=asked,
                forecast_use=own.quantize(QTY),
                planned=already,
                suggested=need,
                can_make=limits.get(item_id),
            )
        )
    return conf.plan_days, sorted(rows, key=lambda r: r.name.lower())
