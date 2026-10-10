"""Best vendor per item (FR-PUR-007): price, real lead time and reliability, from this
tenant's own history only (no marketplace data).

Price: the vendor's current price per base unit. Lead time: average days from order to
receipt (vendor lead history). Reliability: share of orders delivered by the expected date
times the share of ordered quantity that arrived, over the last 180 days; no history counts as
reliable. Effective cost = price x (1 + weight x (1 - reliability)) x (1 + cost per lead day x
lead days), with both weights tenant settings. The lowest effective cost ranks first."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import service as settings
from app.core.settings.schemas import PlanningSettings
from app.modules.catalog.interface import base_factors
from app.modules.purchasing.models import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
    VendorItem,
    VendorLeadHistory,
)

WINDOW_DAYS = 180
DONE = ("partially_received", "received")


@dataclass(frozen=True)
class Score:
    vendor_id: uuid.UUID
    item_id: uuid.UUID
    per_base: Decimal  # current price per base unit
    lead_days: Decimal | None
    on_time: Decimal | None  # 0..1
    fill: Decimal | None  # 0..1
    effective: Decimal  # per base unit, after the penalties
    preferred: bool
    vendor_item: VendorItem


async def _latest(db: AsyncSession, ids: set[uuid.UUID], today: date) -> list[VendorItem]:
    stmt = (
        select(VendorItem)
        .join(Vendor, Vendor.id == VendorItem.vendor_id)
        .where(VendorItem.item_id.in_(ids), VendorItem.valid_from <= today, Vendor.is_active)
        .order_by(VendorItem.valid_from.desc())
    )
    latest: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], VendorItem] = {}
    for vi in await db.scalars(stmt):
        latest.setdefault((vi.item_id, vi.vendor_id, vi.pack_unit_id), vi)
    return list(latest.values())


async def _lead(
    db: AsyncSession, ids: set[uuid.UUID], since: date
) -> dict[tuple[uuid.UUID, uuid.UUID], Decimal]:
    h = VendorLeadHistory
    rows = await db.execute(
        select(h.vendor_id, h.item_id, func.avg(h.received_at - h.ordered_at))
        .where(h.item_id.in_(ids), h.received_at >= since)
        .group_by(h.vendor_id, h.item_id)
    )
    return {(v, i): Decimal(d).quantize(Decimal("0.1")) for v, i, d in rows.all()}


async def _fill(
    db: AsyncSession, ids: set[uuid.UUID], since: date
) -> dict[tuple[uuid.UUID, uuid.UUID], Decimal]:
    ln, po = PurchaseOrderLine, PurchaseOrder
    rows = await db.execute(
        select(po.vendor_id, ln.item_id, func.sum(ln.received_qty), func.sum(ln.qty))
        .join(po, po.id == ln.po_id)
        .where(ln.item_id.in_(ids), po.status.in_(DONE), po.order_date >= since)
        .group_by(po.vendor_id, ln.item_id)
    )
    return {(v, i): min(Decimal(r) / Decimal(q), Decimal(1)) for v, i, r, q in rows.all() if q}


async def _on_time(
    db: AsyncSession, vendors: set[uuid.UUID], since: date
) -> dict[uuid.UUID, Decimal]:
    first = (
        select(GoodsReceipt.po_id, func.min(GoodsReceipt.business_date).label("arrived"))
        .where(GoodsReceipt.po_id.is_not(None), GoodsReceipt.status == "posted")
        .group_by(GoodsReceipt.po_id)
        .subquery()
    )
    po = PurchaseOrder
    on_time = func.count().filter(first.c.arrived <= po.expected_date)
    rows = await db.execute(
        select(po.vendor_id, on_time, func.count())
        .join(first, first.c.po_id == po.id)
        .where(po.vendor_id.in_(vendors), po.expected_date.is_not(None), po.order_date >= since)
        .group_by(po.vendor_id)
    )
    return {v: Decimal(ok) / Decimal(n) for v, ok, n in rows.all() if n}


def _effective(
    price: Decimal, reliability: Decimal, lead: Decimal, conf: PlanningSettings
) -> Decimal:
    penalty = 1 + Decimal(conf.reliability_weight_pct) / 100 * (1 - reliability)
    waiting = 1 + Decimal(conf.lead_day_cost_bp) / 10_000 * lead
    return (price * penalty * waiting).quantize(Decimal("0.000001"), ROUND_HALF_UP)


async def scores(
    db: AsyncSession, tenant_id: uuid.UUID, ids: set[uuid.UUID], today: date
) -> dict[uuid.UUID, list[Score]]:
    """Per item, every active vendor with a current price, best first."""
    conf = cast(PlanningSettings, await settings.get_setting(db, tenant_id, "planning"))
    offers = await _latest(db, ids, today)
    since = today - timedelta(days=WINDOW_DAYS)
    lead, fill = await _lead(db, ids, since), await _fill(db, ids, since)
    on_time = await _on_time(db, {vi.vendor_id for vi in offers}, since)
    factors = await base_factors(db, {(vi.item_id, vi.pack_unit_id) for vi in offers})
    out: dict[uuid.UUID, list[Score]] = {}
    for vi in offers:
        key = (vi.vendor_id, vi.item_id)
        price = Decimal(vi.price) / (vi.pack_qty * factors[(vi.item_id, vi.pack_unit_id)])
        ot, fl = on_time.get(vi.vendor_id), fill.get(key)
        reliability = (ot if ot is not None else Decimal(1)) * (
            fl if fl is not None else Decimal(1)
        )
        days = lead.get(key)
        eff = _effective(price, reliability, days or Decimal(0), conf)
        out.setdefault(vi.item_id, []).append(
            Score(vi.vendor_id, vi.item_id, price, days, ot, fl, eff, vi.is_preferred, vi)
        )
    for rows in out.values():
        rows.sort(key=lambda s: (s.effective, s.lead_days or Decimal(0)))
    return out
