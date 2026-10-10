"""Prime cost (FR-RPT-008): food cost (HPP, the stock value sales took) plus labour, the two
costs a kitchen controls most, against net sales. Labour is typed in per outlet and month;
a period that covers part of a month takes that share of it, by days."""

import calendar
import uuid
from datetime import date, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.reports import Period
from app.modules.finance.models import LaborCost
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.interface import period_totals


class LaborIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outlet_id: uuid.UUID
    month: date  # any day of the month
    amount: Annotated[int, Field(ge=0, le=10**15)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class PrimeCostOut(BaseModel):
    net_sales: int
    food_cost: int
    labor: int
    prime_cost: int
    prime_cost_pct: str | None
    food_cost_pct: str | None
    labor_pct: str | None
    labor_months_missing: list[date]  # months in the period with no labour entered


def _pct(part: int, whole: int) -> str | None:
    return f"{part * 100 / whole:.1f}" if whole else None


def months(start: date, end: date) -> list[date]:
    out, m = [], start.replace(day=1)
    while m <= end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def share(month: date, amount: int, start: date, end: date) -> int:
    """The part of a month's labour that falls inside [start, end], by days."""
    days = calendar.monthrange(month.year, month.month)[1]
    last = month.replace(day=days)
    inside = (min(end, last) - max(start, month)).days + 1
    return round(amount * max(inside, 0) / days)


async def save_labor(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: LaborIn
) -> None:
    await visible_outlet(db, data.outlet_id)
    month = data.month.replace(day=1)
    stmt = insert(LaborCost).values(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        month=month,
        amount=data.amount,
        note=data.note,
        updated_by=user_id,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["tenant_id", "outlet_id", "month"],
            set_={"amount": data.amount, "note": data.note, "updated_by": user_id},
        )
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=data.outlet_id,
        action="finance.labor.save",
        target_type="labor_cost",
        target_id=data.outlet_id,
        summary={"month": month.isoformat(), "amount": data.amount},
    )


async def labor_rows(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None
) -> list[LaborCost]:
    stmt = select(LaborCost).where(
        LaborCost.month >= period.date_from.replace(day=1), LaborCost.month <= period.date_to
    )
    if outlets is not None:
        stmt = stmt.where(LaborCost.outlet_id.in_(outlets))
    return list(await db.scalars(stmt.order_by(LaborCost.month)))


async def prime_cost(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None
) -> PrimeCostOut:
    sales = await period_totals(db, period, outlets)
    rows = await labor_rows(db, period, outlets)
    labor = sum(share(r.month, r.amount, period.date_from, period.date_to) for r in rows)
    entered = {r.month for r in rows}
    prime = sales.cost + labor
    return PrimeCostOut(
        net_sales=sales.net_sales,
        food_cost=sales.cost,
        labor=labor,
        prime_cost=prime,
        prime_cost_pct=_pct(prime, sales.net_sales),
        food_cost_pct=_pct(sales.cost, sales.net_sales),
        labor_pct=_pct(labor, sales.net_sales),
        labor_months_missing=[
            m for m in months(period.date_from, period.date_to) if m not in entered
        ],
    )
