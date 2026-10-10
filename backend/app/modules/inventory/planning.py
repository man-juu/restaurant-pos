"""Days of inventory (FR-INV-011) and reorder needs (FR-INV-013) from the ledger.

Usage = stock that left for sales, production, transfers out and waste over the last four
weeks, averaged per weekday (a Saturday is compared with Saturdays). Days left walks forward
from tomorrow through those weekday averages until the stock on hand is used up."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import items_with_recipe, stock_items, unit_needs
from app.modules.inventory.levels import on_hand_by_item
from app.modules.inventory.models import StockLevel, StockMovement

USE_TYPES = ("sale_consumption", "production_consumption", "transfer_out", "waste")
WEEKS = 4
MAX_DAYS = 365
QTY = Decimal("0.0001")
DEFAULT_LEAD_DAYS = 3  # when neither the level nor the vendor says otherwise


async def weekday_usage(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID], today: date
) -> dict[uuid.UUID, list[Decimal]]:
    """Average base quantity used per weekday (Monday = 0) over the last four weeks."""
    since = today - timedelta(days=7 * WEEKS)
    dow = extract("isodow", StockMovement.business_date)
    stmt = (
        select(StockMovement.item_id, dow, func.sum(-StockMovement.qty))
        .where(
            StockMovement.outlet_id == outlet_id,
            StockMovement.item_id.in_(ids),
            StockMovement.movement_type.in_(USE_TYPES),
            StockMovement.business_date > since,
            StockMovement.business_date <= today,
        )
        .group_by(StockMovement.item_id, dow)
    )
    out: dict[uuid.UUID, list[Decimal]] = {}
    for item_id, day, used in (await db.execute(stmt)).all():
        week = out.setdefault(item_id, [Decimal(0)] * 7)
        week[int(day) - 1] = max(Decimal(used), Decimal(0)) / WEEKS
    return out


def average_daily(week: list[Decimal]) -> Decimal:
    return (sum(week, Decimal(0)) / 7).quantize(QTY, ROUND_HALF_UP)


def days_left(on_hand: Decimal, week: list[Decimal] | None, today: date) -> Decimal | None:
    """None when nothing was used lately (no estimate); 0 when nothing is left."""
    if not week or not any(week):
        return None
    if on_hand <= 0:
        return Decimal(0)
    left, day = on_hand, today
    for n in range(MAX_DAYS):
        day += timedelta(days=1)
        use = week[day.weekday()]
        if use >= left:
            return (Decimal(n) + left / use).quantize(Decimal("0.1"), ROUND_HALF_UP)
        left -= use
    return Decimal(MAX_DAYS)


@dataclass(frozen=True)
class Need:
    item_id: uuid.UUID
    on_hand: Decimal
    reorder_point: Decimal
    suggested: Decimal  # base unit, enough to reach the target
    avg_daily: Decimal
    eoq: Decimal | None = None  # FR-INV-018, base unit, when the tenant set an order cost


async def reorder_needs(db: AsyncSession, outlet_id: uuid.UUID, today: date) -> list[Need]:
    """Items at or below their reorder point. Target: the maximum level if set, otherwise
    the reorder point plus safety stock plus usage over the lead time."""
    levels = list(
        await db.scalars(
            select(StockLevel).where(
                StockLevel.outlet_id == outlet_id, StockLevel.reorder_point.is_not(None)
            )
        )
    )
    ids = {lv.item_id for lv in levels}
    have = await on_hand_by_item(db, outlet_id, ids)
    usage = await weekday_usage(db, outlet_id, ids, today)
    needs = []
    for lv in levels:
        q, point = have.get(lv.item_id, Decimal(0)), lv.reorder_point or Decimal(0)
        if q > point:
            continue
        daily = average_daily(usage.get(lv.item_id, [Decimal(0)] * 7))
        lead = lv.lead_time_days if lv.lead_time_days is not None else DEFAULT_LEAD_DAYS
        target = lv.max_qty or point + (lv.safety_qty or Decimal(0)) + daily * lead
        suggested = max(target - q, Decimal(0)).quantize(QTY, ROUND_CEILING)
        if suggested > 0:
            needs.append(Need(lv.item_id, q, point, suggested, daily))
    return needs


@dataclass(frozen=True)
class Producible:
    item_id: uuid.UUID
    can_make: Decimal  # whole base units of the item
    limiting_item_id: uuid.UUID | None


async def producible(db: AsyncSession, outlet_id: uuid.UUID, today: date) -> list[Producible]:
    """FR-INV-020: how much of each item with a recipe the stock here can still make, and
    which ingredient runs out first. Components that are not stocked (gas) do not limit."""
    recipes = await unit_needs(db, await items_with_recipe(db, today), today)
    comps = {c for need in recipes.values() for c in need}
    items = await stock_items(db, comps)
    have = await on_hand_by_item(db, outlet_id, comps)
    out = []
    for item_id, need in recipes.items():
        limits = [
            (max(have.get(c, Decimal(0)), Decimal(0)) / per, c)
            for c, per in need.items()
            if per > 0 and c in items and items[c].is_stocked
        ]
        if not limits:
            continue
        qty, limiting = min(limits, key=lambda x: x[0])
        out.append(Producible(item_id, qty.to_integral_value(ROUND_FLOOR), limiting))
    return out
