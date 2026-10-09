"""Tax collected (FR-FIN-008) and sales by staff (FR-RPT-012), over this module's tables.
Both use posted documents only (replaced, reversed and refunded sales are left out)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet, User
from app.core.reports import Period, Report, build
from app.modules.sales.models import PosOrder, SalesDocument
from app.modules.sales.reports import NET, _live


async def tax_report(db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None) -> Report:
    """Per outlet and day: sales, service charge and the tax collected on them (the regional
    PBJT/PB1 return is filed from these figures)."""
    stmt = _live(
        select(
            SalesDocument.business_date,
            Outlet.name,
            func.count(SalesDocument.id),
            func.sum(NET),
            func.sum(SalesDocument.service_charge),
            func.sum(SalesDocument.tax),
        )
        .join(Outlet, Outlet.id == SalesDocument.outlet_id)
        .group_by(SalesDocument.business_date, Outlet.name)
        .order_by(SalesDocument.business_date, Outlet.name),
        period,
        outlets,
    )
    rows = [
        {
            "date": day.isoformat(),
            "outlet": outlet,
            "sales": docs,
            "net_sales": int(net),
            "service_charge": int(service),
            "tax": int(tax),
        }
        for day, outlet, docs, net, service, tax in (await db.execute(stmt)).all()
    ]
    totals = {
        key: sum(r[key] for r in rows) for key in ("sales", "net_sales", "service_charge", "tax")
    }
    return build(["date", "outlet", "sales", "net_sales", "service_charge", "tax"], rows, totals)


async def staff_report(db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None) -> Report:
    """POS orders per person who took the payment: count, net sales, average order."""
    who = PosOrder.paid_by
    stmt = _live(
        select(who, User.name, func.count(SalesDocument.id), func.sum(NET))
        .join(PosOrder, PosOrder.document_id == SalesDocument.id)
        .join(User, User.id == who)
        .where(SalesDocument.source == "pos")
        .group_by(who, User.name)
        .order_by(func.sum(NET).desc()),
        period,
        outlets,
    )
    rows = [
        {
            "staff": name,
            "orders": n,
            "net_sales": int(net),
            "average_order": int(net) // n if n else 0,
        }
        for _, name, n, net in (await db.execute(stmt)).all()
    ]
    return build(["staff", "orders", "net_sales", "average_order"], rows)


@dataclass(frozen=True)
class PeriodTotals:
    net_sales: int  # list value minus discounts
    service_charge: int
    tax: int
    cost: int  # stock value the sales took (HPP)
    documents: int


async def period_totals(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None
) -> PeriodTotals:
    stmt = _live(
        select(
            func.coalesce(func.sum(NET), 0),
            func.coalesce(func.sum(SalesDocument.service_charge), 0),
            func.coalesce(func.sum(SalesDocument.tax), 0),
            func.coalesce(func.sum(SalesDocument.cost), 0),
            func.count(SalesDocument.id),
        ),
        period,
        outlets,
    )
    net, service, tax, cost, docs = (await db.execute(stmt)).one()
    return PeriodTotals(int(net), int(service), int(tax), int(cost), int(docs))
