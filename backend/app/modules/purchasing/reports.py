"""Purchase reports (FR-RPT-005): what was bought, from whom, and how prices moved.
Amounts are cost data: shown only with catalog.cost.view."""

import uuid
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reports import Period, Report, build
from app.modules.catalog.interface import item_names
from app.modules.purchasing.models import GoodsReceipt, GoodsReceiptLine, Vendor, VendorPriceHistory

By = Literal["vendor", "item"]


def _posted(stmt: Any, period: Period, outlets: list[uuid.UUID] | None) -> Any:
    stmt = stmt.where(
        GoodsReceipt.status == "posted",
        GoodsReceipt.business_date >= period.date_from,
        GoodsReceipt.business_date <= period.date_to,
    )
    return stmt if outlets is None else stmt.where(GoodsReceipt.outlet_id.in_(outlets))


async def purchases(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    by: By,
    *,
    language: str,
    show_cost: bool,
) -> Report:
    if by == "vendor":
        name = func.coalesce(Vendor.name, GoodsReceipt.vendor_name, "")
        stmt = _posted(
            select(name, func.count(GoodsReceipt.id), func.sum(GoodsReceipt.total))
            .outerjoin(Vendor, Vendor.id == GoodsReceipt.vendor_id)
            .group_by(name),
            period,
            outlets,
        )
        found = [(n, c, t) for n, c, t in (await db.execute(stmt)).all()]
    else:
        stmt = _posted(
            select(
                GoodsReceiptLine.item_id,
                func.count(GoodsReceiptLine.id),
                func.sum(GoodsReceiptLine.line_total),
            )
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.receipt_id)
            .group_by(GoodsReceiptLine.item_id),
            period,
            outlets,
        )
        raw = (await db.execute(stmt)).all()
        names = await item_names(db, tenant_id, language, {r[0] for r in raw})
        found = [(names[i].name, c, t) for i, c, t in raw]
    rows = [
        {"name": n, "receipts": c, **({"total": int(t)} if show_cost else {})} for n, c, t in found
    ]
    rows.sort(key=lambda r: (-r.get("total", 0), r["name"].lower()))
    totals = {"total": sum(r.get("total", 0) for r in rows)} if show_cost else {}
    return build(["name", "receipts"] + (["total"] if show_cost else []), rows, totals)


async def price_trend(db: AsyncSession, period: Period, item_id: uuid.UUID) -> Report:
    """Every observed unit cost (per base unit) of the item in the period, by vendor."""
    stmt = (
        select(
            VendorPriceHistory.observed_at,
            func.coalesce(Vendor.name, ""),
            VendorPriceHistory.unit_cost,
        )
        .outerjoin(Vendor, Vendor.id == VendorPriceHistory.vendor_id)
        .where(
            VendorPriceHistory.item_id == item_id,
            VendorPriceHistory.observed_at >= period.date_from,
            VendorPriceHistory.observed_at <= period.date_to,
        )
        .order_by(VendorPriceHistory.observed_at)
    )
    rows = [
        {"date": d.isoformat(), "vendor": v, "unit_cost": f"{c.normalize():f}"}
        for d, v, c in (await db.execute(stmt)).all()
    ]
    return build(["date", "vendor", "unit_cost"], rows)
