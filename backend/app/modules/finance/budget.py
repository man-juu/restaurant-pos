"""Budgets (FR-FIN-010): a plan per outlet and month for net sales, cost of sales (HPP),
labour and other expenses, compared with what happened. Actuals come from the same sources
as profit and loss and prime cost, so the numbers agree across screens."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.reports import Period
from app.modules.finance import prime, service
from app.modules.finance.models import Budget
from app.modules.inventory.interface import visible_outlet

Amount = Annotated[int, Field(ge=0, le=10**15)]
LINES = ("net_sales", "cost_of_sales", "labor", "expenses")
# Lines where spending more than planned is bad (net sales: less is bad).
COSTS = ("cost_of_sales", "labor", "expenses")


class BudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outlet_id: uuid.UUID
    month: date  # any day of the month
    net_sales: Amount
    cost_of_sales: Amount
    labor: Amount
    expenses: Amount


class BudgetOut(BudgetIn):
    pass


class BudgetLine(BaseModel):
    line: str  # net_sales, cost_of_sales, labor, expenses, net_profit
    budget: int
    actual: int
    variance: int  # actual - budget
    variance_pct: str | None
    favourable: bool


class BudgetReport(BaseModel):
    lines: list[BudgetLine]
    months_missing: list[date]  # months in the period with no budget for some outlet asked


async def save(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: BudgetIn
) -> None:
    await visible_outlet(db, data.outlet_id)
    month = data.month.replace(day=1)
    values = {k: getattr(data, k) for k in LINES}
    stmt = insert(Budget).values(
        tenant_id=tenant_id, outlet_id=data.outlet_id, month=month, updated_by=user_id, **values
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["tenant_id", "outlet_id", "month"],
            set_={**values, "updated_by": user_id},
        )
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=data.outlet_id,
        action="finance.budget.save",
        target_type="budget",
        target_id=data.outlet_id,
        summary={"month": month.isoformat(), **values},
    )


async def rows(db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None) -> list[Budget]:
    stmt = select(Budget).where(
        Budget.month >= period.date_from.replace(day=1), Budget.month <= period.date_to
    )
    if outlets is not None:
        stmt = stmt.where(Budget.outlet_id.in_(outlets))
    return list(await db.scalars(stmt.order_by(Budget.month, Budget.outlet_id)))


def _line(line: str, budget: int, actual: int) -> BudgetLine:
    variance = actual - budget
    good = variance <= 0 if line in COSTS else variance >= 0
    pct = f"{variance * 100 / budget:.1f}" if budget else None
    return BudgetLine(
        line=line,
        budget=budget,
        actual=actual,
        variance=variance,
        variance_pct=pct,
        favourable=good,
    )


def _missing(period: Period, saved: list[Budget], outlets: list[uuid.UUID] | None) -> list[date]:
    have: dict[date, set[uuid.UUID]] = {}
    for r in saved:
        have.setdefault(r.month, set()).add(r.outlet_id)
    need = set(outlets) if outlets is not None else None
    out = []
    for m in prime.months(period.date_from, period.date_to):
        got = have.get(m, set())
        if not got or (need is not None and not need <= got):
            out.append(m)
    return out


async def report(db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None) -> BudgetReport:
    saved = await rows(db, period, outlets)
    a, b = period.date_from, period.date_to
    plan = {k: sum(prime.share(r.month, getattr(r, k), a, b) for r in saved) for k in LINES}
    pl = await service.profit_loss(db, period, outlets)
    labor = sum(
        prime.share(r.month, r.amount, a, b) for r in await prime.labor_rows(db, period, outlets)
    )
    actual = {
        "net_sales": pl.net_sales,
        "cost_of_sales": pl.cost_of_sales,
        "labor": labor,
        "expenses": pl.expenses_total,
    }
    lines = [_line(k, plan[k], actual[k]) for k in LINES]
    profit = [plan["net_sales"], actual["net_sales"]]
    for k in COSTS:
        profit = [profit[0] - plan[k], profit[1] - actual[k]]
    lines.append(_line("net_profit", *profit))
    return BudgetReport(lines=lines, months_missing=_missing(period, saved, outlets))
