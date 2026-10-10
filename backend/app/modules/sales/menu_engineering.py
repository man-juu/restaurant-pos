"""Menu engineering (FR-RPT-007), the Kasavana-Smith matrix, over the period's posted sales.

Per menu item: quantity sold, net sales and contribution margin (net per portion minus the
recipe's cost today). Popular: the item's share of portions sold is at least
`menu_popularity_pct` of a fair share (100 % / number of items; 70 % by default). Profitable:
its margin per portion is at least the menu's weighted average. Then
star = popular and profitable, plowhorse = popular only, puzzle = profitable only, dog = neither.
Items without a known cost are listed as "no_cost" and left out of the averages."""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reports import Period, Report, build
from app.core.settings import service as settings
from app.core.settings.schemas import ReportSettings
from app.modules.catalog.interface import item_names, stock_items
from app.modules.sales.models import SalesDocument, SalesLine
from app.modules.sales.reports import _line_net, _live, _unit_costs

COLUMNS = ["name", "qty", "net_sales", "unit_margin", "total_margin", "mix_pct", "class"]


def classify(popular: bool, profitable: bool) -> str:
    if popular:
        return "star" if profitable else "plowhorse"
    return "puzzle" if profitable else "dog"


async def _sold(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    stmt = _live(
        select(SalesLine.item_id, func.sum(SalesLine.qty), func.sum(_line_net()))
        .join(SalesDocument, SalesDocument.id == SalesLine.document_id)
        .group_by(SalesLine.item_id),
        period,
        outlets,
    )
    rows = (await db.execute(stmt)).all()
    return {i: (Decimal(q), Decimal(n or 0)) for i, q, n in rows if q and q > 0}


def _rows(
    sold: dict[uuid.UUID, tuple[Decimal, Decimal]],
    costs: dict[uuid.UUID, Decimal],
    names: dict[uuid.UUID, Any],
    popularity_pct: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_qty = sum((q for q, _ in sold.values()), Decimal(0))
    costed = {i: v for i, v in sold.items() if i in costs}
    margin = {i: n - q * costs[i] for i, (q, n) in costed.items()}
    costed_qty = sum((q for q, _ in costed.values()), Decimal(0))
    avg_margin = sum(margin.values(), Decimal(0)) / costed_qty if costed_qty else Decimal(0)
    fair = Decimal(100) / len(sold) if sold else Decimal(0)
    bar = fair * popularity_pct / 100
    rows = []
    for item_id, (qty, net) in sold.items():
        mix = qty * 100 / total_qty if total_qty else Decimal(0)
        row: dict[str, Any] = {
            "name": names[item_id].name if item_id in names else "-",
            "qty": f"{qty.normalize():f}",
            "net_sales": int(net),
            "mix_pct": f"{mix:.1f}",
            "unit_margin": None,
            "total_margin": None,
            "class": "no_cost",
        }
        if item_id in margin:
            unit = margin[item_id] / qty
            row |= {
                "unit_margin": int(unit.quantize(Decimal(1), ROUND_HALF_UP)),
                "total_margin": int(margin[item_id].quantize(Decimal(1), ROUND_HALF_UP)),
                "class": classify(mix >= bar, unit >= avg_margin),
            }
        rows.append(row)
    rows.sort(key=lambda r: (-(r["total_margin"] or 0), r["name"]))
    totals = {
        "items": len(sold),
        "popularity_bar_pct": f"{bar:.1f}",
        "average_unit_margin": int(avg_margin.quantize(Decimal(1), ROUND_HALF_UP)),
    }
    return rows, totals


async def report(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    language: str,
) -> Report:
    sold = await _sold(db, period, outlets)
    items = await stock_items(db, sold)
    sold = {i: v for i, v in sold.items() if i in items and items[i].type == "menu"}
    conf = cast(ReportSettings, await settings.get_setting(db, tenant_id, "reports"))
    costs = await _unit_costs(db, tenant_id, set(sold), language)
    names = await item_names(db, tenant_id, language, sold)
    rows, totals = _rows(sold, costs, names, conf.menu_popularity_pct)
    return build(COLUMNS, rows, totals)
