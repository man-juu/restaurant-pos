"""Daily prep list (FR-PRD-008): semi-finished items below their par level at an outlet or
asked for by other outlets (open transfer requests, when the tenant counts them), with what
is already planned for the day and the suggested quantity to make:
par + requested - on hand - planned, never below 0."""

import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demand import outgoing_demand
from app.core.settings import service as settings
from app.core.settings.schemas import ProductionSettings
from app.modules.catalog.interface import item_names, stock_items
from app.modules.inventory.interface import par_and_on_hand
from app.modules.production.models import ProductionOrder
from app.modules.production.schemas import PrepRow

PREP_TYPES = frozenset({"semi_finished"})


async def _planned(db: AsyncSession, outlet_id: uuid.UUID, on: date) -> dict[uuid.UUID, Decimal]:
    stmt = (
        select(ProductionOrder.item_id, func.sum(ProductionOrder.planned_qty))
        .where(
            ProductionOrder.outlet_id == outlet_id,
            ProductionOrder.production_date == on,
            ProductionOrder.status == "planned",
        )
        .group_by(ProductionOrder.item_id)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def _requested(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, on: date
) -> dict[uuid.UUID, Decimal]:
    conf = cast(ProductionSettings, await settings.get_setting(db, tenant_id, "production"))
    if not conf.prep_includes_requests:
        return {}
    return await outgoing_demand(db, tenant_id, outlet_id, on)


async def prep_list(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, on: date, language: str
) -> list[PrepRow]:
    requested = await _requested(db, tenant_id, outlet_id, on)
    levels = await par_and_on_hand(db, outlet_id, set(requested))
    wanted = {i for i, (par, have) in levels.items() if have < par or requested.get(i)}
    items = await stock_items(db, wanted)
    ids = {i for i, it in items.items() if it.type in PREP_TYPES and it.is_active}
    names = await item_names(db, tenant_id, language, ids)
    planned = await _planned(db, outlet_id, on)
    rows = []
    for item_id in ids:
        par, have = levels[item_id]
        asked = requested.get(item_id, Decimal(0))
        already = planned.get(item_id, Decimal(0))
        rows.append(
            PrepRow(
                item_id=item_id,
                sku=names[item_id].sku,
                name=names[item_id].name,
                unit_code=names[item_id].unit_code,
                par_qty=par,
                on_hand=have,
                requested=asked,
                planned=already,
                suggested=max(par + asked - have - already, Decimal(0)),
            )
        )
    return sorted(rows, key=lambda r: r.name.lower())
