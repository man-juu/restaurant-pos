"""Demand forecast and economic order quantity (FR-INV-018).

Forecast: usage (sales, production, transfers out, waste) averaged per weekday over the last
`forecast_weeks` weeks, times a trend: the average of the recent half of those weeks against
the whole, kept between 0.5 and 1.5 so one odd week cannot swing it. Items with less history
than `forecast_min_days` get the plain four-week weekday average and no trend.

EOQ = sqrt(2 x yearly demand x cost per order / yearly holding cost per unit), capped so an
order is used up within the item's shelf life. Off while the tenant's order cost is 0."""

import uuid
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet
from app.core.settings import service as settings
from app.core.settings.schemas import PlanningSettings
from app.modules.catalog.interface import stock_items
from app.modules.inventory.models import ItemCost, StockMovement
from app.modules.inventory.planning import (
    USE_TYPES,
    Need,
    average_daily,
    reorder_needs,
    weekday_usage,
)

QTY = Decimal("0.0001")
TREND_MIN, TREND_MAX = Decimal("0.5"), Decimal("1.5")


@dataclass(frozen=True)
class Forecast:
    item_id: uuid.UUID
    enough_history: bool
    trend: Decimal  # 1 = steady
    weekday: list[Decimal]  # expected use per weekday, Monday first, trend applied
    daily: Decimal  # average per day

    def days(self, start: date, n: int) -> list[Decimal]:
        return [self.weekday[(start + timedelta(days=k)).weekday()] for k in range(n)]


async def planning_settings(db: AsyncSession, outlet_id: uuid.UUID) -> PlanningSettings:
    outlet = await db.get(Outlet, outlet_id)
    tenant_id = outlet.tenant_id if outlet else uuid.UUID(int=0)
    return cast(PlanningSettings, await settings.get_setting(db, tenant_id, "planning"))


async def _history(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID], weeks: int, today: date
) -> tuple[dict[uuid.UUID, list[Decimal]], dict[uuid.UUID, Decimal], dict[uuid.UUID, date]]:
    """Per item: weekday averages over `weeks`, the average per day of the recent half, and
    the first day the item was used here."""
    since = today - timedelta(days=7 * weeks)
    half = today - timedelta(days=7 * (weeks // 2))
    used = func.sum(-StockMovement.qty)
    base = select(StockMovement.item_id).where(
        StockMovement.outlet_id == outlet_id,
        StockMovement.item_id.in_(ids),
        StockMovement.movement_type.in_(USE_TYPES),
        StockMovement.business_date <= today,
    )
    dow = extract("isodow", StockMovement.business_date)
    week_rows = await db.execute(
        base.add_columns(dow, used)
        .where(StockMovement.business_date > since)
        .group_by(StockMovement.item_id, dow)
    )
    weekday: dict[uuid.UUID, list[Decimal]] = {}
    for item_id, day, qty in week_rows.all():
        weekday.setdefault(item_id, [Decimal(0)] * 7)[int(day) - 1] = max(qty, 0) / weeks
    recent_rows = await db.execute(
        base.add_columns(used)
        .where(StockMovement.business_date > half)
        .group_by(StockMovement.item_id)
    )
    recent = {i: max(q, 0) / (7 * (weeks // 2)) for i, q in recent_rows.all()}
    first_rows = await db.execute(
        base.add_columns(func.min(StockMovement.business_date)).group_by(StockMovement.item_id)
    )
    return weekday, recent, dict(first_rows.tuples().all())


def _trend(recent: Decimal, week: list[Decimal]) -> Decimal:
    overall = sum(week, Decimal(0)) / 7
    if overall <= 0:
        return Decimal(1)
    return min(max(recent / overall, TREND_MIN), TREND_MAX).quantize(Decimal("0.01"))


async def forecasts(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID], today: date
) -> dict[uuid.UUID, Forecast]:
    conf = await planning_settings(db, outlet_id)
    weekday, recent, first = await _history(db, outlet_id, ids, conf.forecast_weeks, today)
    plain = await weekday_usage(db, outlet_id, ids, today)
    out = {}
    for item_id in ids:
        started = first.get(item_id)
        enough = started is not None and (today - started).days >= conf.forecast_min_days
        if enough:
            week = weekday.get(item_id, [Decimal(0)] * 7)
            trend = _trend(recent.get(item_id, Decimal(0)), week)
            week = [(d * trend).quantize(QTY, ROUND_HALF_UP) for d in week]
        else:
            week, trend = plain.get(item_id, [Decimal(0)] * 7), Decimal(1)
        out[item_id] = Forecast(item_id, enough, trend, week, average_daily(week))
    return out


def eoq(
    daily: Decimal, unit_cost: Decimal | None, conf: PlanningSettings, shelf_life: int | None
) -> Decimal | None:
    """Economic order quantity in base units, or None when it cannot be worked out."""
    if conf.order_cost <= 0 or daily <= 0 or not unit_cost or unit_cost <= 0:
        return None
    yearly_holding = unit_cost * conf.holding_cost_pct / 100
    qty = (2 * daily * 365 * conf.order_cost / yearly_holding).sqrt()
    if shelf_life:
        qty = min(qty, daily * shelf_life)
    return qty.quantize(QTY, ROUND_CEILING)


async def unit_costs(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    rows = await db.execute(
        select(ItemCost.item_id, ItemCost.avg_cost).where(
            ItemCost.outlet_id == outlet_id, ItemCost.item_id.in_(ids)
        )
    )
    return dict(rows.tuples().all())


async def needs_with_eoq(db: AsyncSession, outlet_id: uuid.UUID, today: date) -> list[Need]:
    """Reorder needs (FR-INV-013) with the economic order quantity alongside."""
    needs = await reorder_needs(db, outlet_id, today)
    conf = await planning_settings(db, outlet_id)
    if conf.order_cost <= 0 or not needs:
        return needs
    ids = {n.item_id for n in needs}
    ahead = await forecasts(db, outlet_id, ids, today)
    costs = await unit_costs(db, outlet_id, ids)
    items = await stock_items(db, ids)
    return [
        replace(
            n,
            eoq=eoq(
                ahead[n.item_id].daily,
                costs.get(n.item_id),
                conf,
                items[n.item_id].shelf_life_days if n.item_id in items else None,
            ),
        )
        for n in needs
    ]


async def used_items(db: AsyncSession, outlet_id: uuid.UUID, today: date) -> set[uuid.UUID]:
    """Items used at the outlet in the last eight weeks (the forecast list)."""
    rows = await db.scalars(
        select(StockMovement.item_id)
        .where(
            StockMovement.outlet_id == outlet_id,
            StockMovement.movement_type.in_(USE_TYPES),
            StockMovement.business_date > today - timedelta(days=56),
        )
        .distinct()
        .limit(2000)
    )
    return set(rows)
