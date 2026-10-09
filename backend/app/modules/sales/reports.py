"""Sales reports (FR-RPT-001 to 003, 011) over this module's own tables.

Net sales = list value minus promo discount (before service charge and tax). Food cost (HPP)
is the stock value the day's recipes took out; shown only with catalog.cost.view."""

import uuid
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet
from app.core.reports import Period, Report, build
from app.modules.catalog.interface import (
    channel_names,
    costing,
    item_categories,
    item_names,
    tenant_today,
)
from app.modules.sales.models import SalesDocument, SalesLine

Grain = Literal["day", "week", "month"]
Dimension = Literal["outlet", "channel", "item", "category", "weekday"]
NET = SalesDocument.subtotal - SalesDocument.discount


def _live(stmt: Any, period: Period, outlets: list[uuid.UUID] | None) -> Any:
    stmt = stmt.where(
        SalesDocument.status == "posted",
        SalesDocument.business_date >= period.date_from,
        SalesDocument.business_date <= period.date_to,
    )
    return stmt if outlets is None else stmt.where(SalesDocument.outlet_id.in_(outlets))


def _pct(part: int, whole: int) -> str | None:
    return f"{Decimal(part) * 100 / whole:.1f}" if whole else None


async def _net(db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None) -> int:
    return int(
        await db.scalar(_live(select(func.coalesce(func.sum(NET), 0)), period, outlets)) or 0
    )


async def summary(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None, grain: Grain, show_cost: bool
) -> Report:
    """FR-RPT-011: per outlet and day, week or month; previous-period comparison; best days."""
    start = func.date_trunc(grain, SalesDocument.business_date).cast(
        SalesDocument.business_date.type
    )
    stmt = _live(
        select(
            start.label("start"),
            Outlet.name,
            func.count(SalesDocument.id),
            func.sum(NET),
            func.sum(SalesDocument.discount),
            func.sum(SalesDocument.total),
            func.sum(SalesDocument.cost),
        )
        .join(Outlet, Outlet.id == SalesDocument.outlet_id)
        .group_by(start, Outlet.name)
        .order_by(start, Outlet.name),
        period,
        outlets,
    )
    rows = []
    for st, outlet, docs, net, disc, total, cost in (await db.execute(stmt)).all():
        row = {
            "period": st.isoformat(),
            "outlet": outlet,
            "entries": docs,
            "net_sales": int(net),
            "discount": int(disc),
            "total": int(total),
        }
        if show_cost:
            row |= {"food_cost": int(cost), "food_cost_pct": _pct(int(cost), int(net))}
        rows.append(row)
    best = await db.execute(
        _live(select(SalesDocument.business_date, func.sum(NET).label("n")), period, outlets)
        .group_by(SalesDocument.business_date)
        .order_by(func.sum(NET).desc())
        .limit(3)
    )
    net_now = sum(r["net_sales"] for r in rows)
    net_before = await _net(db, period.previous(), outlets)
    totals = {
        "net_sales": net_now,
        "previous_net_sales": net_before,
        "change_pct": _pct(net_now - net_before, net_before),
        "best_days": [{"date": d.isoformat(), "net_sales": int(n)} for d, n in best.all()],
    }
    cols = ["period", "outlet", "entries", "net_sales", "discount", "total"]
    return build(cols + (["food_cost", "food_cost_pct"] if show_cost else []), rows, totals)


def _line_net() -> Any:
    """A line's share of its document's net sales (promo discount spread by value)."""
    value = SalesLine.qty * SalesLine.unit_price
    return value * NET / func.nullif(SalesDocument.subtotal, 0)


async def breakdown(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    by: Dimension,
    *,
    language: str,
    show_cost: bool,
) -> Report:
    """FR-RPT-001 to 003: net sales by outlet, channel, item, category or weekday; items and
    categories also show quantity and, with cost view, theoretical food cost and margin."""
    if by in ("outlet", "channel", "weekday"):
        return await _by_document(db, period, outlets, by, show_cost)
    stmt = _live(
        select(SalesLine.item_id, func.sum(SalesLine.qty), func.sum(_line_net()))
        .join(SalesDocument, SalesDocument.id == SalesLine.document_id)
        .group_by(SalesLine.item_id),
        period,
        outlets,
    )
    sold = {i: (q, Decimal(n or 0)) for i, q, n in (await db.execute(stmt)).all()}
    names = await item_names(db, tenant_id, language, sold)
    unit_cost = await _unit_costs(db, tenant_id, set(sold), language) if show_cost else {}
    rows = [_item_row(names[i].name, q, n, unit_cost.get(i)) for i, (q, n) in sold.items()]
    if by == "category":
        rows = await _by_category(db, sold, rows)
    rows.sort(key=lambda r: -r["net_sales"])
    cols = ["name", "qty", "net_sales"] + (
        ["food_cost", "food_cost_pct", "margin"] if show_cost else []
    )
    return build(cols, rows)


def _item_row(name: str, qty: Decimal, net: Decimal, unit_cost: Decimal | None) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "qty": f"{qty.normalize():f}", "net_sales": int(net)}
    if unit_cost is not None:
        cost = int(qty * unit_cost)
        row |= {"food_cost": cost, "food_cost_pct": _pct(cost, int(net)), "margin": int(net) - cost}
    return row


async def _unit_costs(
    db: AsyncSession, tenant_id: uuid.UUID, ids: set[uuid.UUID], language: str
) -> dict[uuid.UUID, Decimal]:
    """Theoretical cost of one unit of each item at today's costs (FR-RPT-003)."""
    today = await tenant_today(db, tenant_id)
    out = {}
    for item_id in ids:
        c = await costing(
            db, tenant_id=tenant_id, item_id=item_id, on=today, language=language, show_cost=True
        )
        if c.cost is not None:
            out[item_id] = c.cost
    return out


async def _by_category(
    db: AsyncSession, sold: dict[uuid.UUID, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    cats = await item_categories(db, sold)
    out: dict[str, dict[str, Any]] = {}
    for item_id, row in zip(sold, rows, strict=True):
        name = cats.get(item_id, (None, None))[1] or "-"
        acc = out.setdefault(name, {"name": name, "qty": "", "net_sales": 0})
        acc["net_sales"] += row["net_sales"]
        if "food_cost" in row:
            acc["food_cost"] = acc.get("food_cost", 0) + row["food_cost"]
    for acc in out.values():
        if "food_cost" in acc:
            acc["food_cost_pct"] = _pct(acc["food_cost"], acc["net_sales"])
            acc["margin"] = acc["net_sales"] - acc["food_cost"]
    return list(out.values())


async def _by_document(
    db: AsyncSession,
    period: Period,
    outlets: list[uuid.UUID] | None,
    by: Dimension,
    show_cost: bool,
) -> Report:
    key: Any = {
        "outlet": SalesDocument.outlet_id,
        "channel": SalesDocument.channel_id,
        "weekday": extract("isodow", SalesDocument.business_date),
    }[by]
    stmt = _live(
        select(key, func.count(), func.sum(NET), func.sum(SalesDocument.cost)).group_by(key),
        period,
        outlets,
    )
    labels = await _labels(db, by)
    rows = []
    for k, n, net, cost in (await db.execute(stmt)).all():
        row: dict[str, Any] = {"name": labels.get(k, str(k)), "entries": n, "net_sales": int(net)}
        if show_cost:
            row |= {"food_cost": int(cost), "food_cost_pct": _pct(int(cost), int(net))}
        rows.append(row)
    rows.sort(key=lambda r: -r["net_sales"])
    return build(
        ["name", "entries", "net_sales"] + (["food_cost", "food_cost_pct"] if show_cost else []),
        rows,
    )


async def _labels(db: AsyncSession, by: Dimension) -> dict[Any, str]:
    if by == "outlet":
        return dict((await db.execute(select(Outlet.id, Outlet.name))).all())
    if by == "channel":
        return await channel_names(db)
    return {Decimal(d): str(d) for d in range(1, 8)}  # ISO weekday; the screen names it
