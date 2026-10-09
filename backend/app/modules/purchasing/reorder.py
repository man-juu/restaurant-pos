"""Reorder suggestions (FR-INV-013): items at or below their reorder point at an outlet,
grouped by vendor, with quantities in the vendor's packs, ready to become a draft PO.

Vendor per item: the vendor item marked preferred, else the cheapest per base unit among
active vendors' current prices. Prices and packs are the latest from each vendor."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import base_factors, item_names, tenant_today
from app.modules.inventory.interface import Need, reorder_needs
from app.modules.purchasing.models import Vendor, VendorItem
from app.modules.purchasing.schemas import SuggestionGroup, SuggestionLine


@dataclass(frozen=True)
class Offer:
    vendor_id: uuid.UUID
    pack_qty: Decimal
    pack_unit_id: uuid.UUID
    price: int
    min_packs: Decimal | None
    preferred: bool
    per_base: Decimal  # price per base unit, to compare vendors


async def _offers(db: AsyncSession, ids: set[uuid.UUID], today: date) -> dict[uuid.UUID, Offer]:
    stmt = (
        select(VendorItem)
        .join(Vendor, Vendor.id == VendorItem.vendor_id)
        .where(VendorItem.item_id.in_(ids), VendorItem.valid_from <= today, Vendor.is_active)
        .order_by(VendorItem.valid_from.desc())
    )
    latest: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], VendorItem] = {}
    for vi in await db.scalars(stmt):
        latest.setdefault((vi.item_id, vi.vendor_id, vi.pack_unit_id), vi)
    factors = await base_factors(db, {(vi.item_id, vi.pack_unit_id) for vi in latest.values()})
    best: dict[uuid.UUID, Offer] = {}
    for vi in latest.values():
        base = vi.pack_qty * factors[(vi.item_id, vi.pack_unit_id)]
        offer = Offer(
            vi.vendor_id,
            vi.pack_qty,
            vi.pack_unit_id,
            vi.price,
            vi.min_order_qty,
            vi.is_preferred,
            Decimal(vi.price) / base,
        )
        now = best.get(vi.item_id)
        if now is None or (offer.preferred, -offer.per_base) > (now.preferred, -now.per_base):
            best[vi.item_id] = offer
    return best


def _line(
    need: Need, offer: Offer | None, factor: Decimal | None, label: tuple[str, str]
) -> SuggestionLine:
    order_qty = unit_price = unit = None
    if offer and factor:
        packs = (need.suggested / (offer.pack_qty * factor)).to_integral_value(ROUND_CEILING)
        packs = max(packs, offer.min_packs or Decimal(0))
        order_qty, unit = packs * offer.pack_qty, offer.pack_unit_id
        unit_price = int(
            (Decimal(offer.price) / offer.pack_qty).quantize(Decimal(1), ROUND_HALF_UP)
        )
    return SuggestionLine(
        item_id=need.item_id,
        name=label[0],
        unit_code=label[1],
        on_hand=need.on_hand,
        reorder_point=need.reorder_point,
        suggested=need.suggested,
        order_qty=order_qty,
        order_unit_id=unit,
        unit_price=unit_price,
    )


async def suggestions(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, language: str
) -> list[SuggestionGroup]:
    today = await tenant_today(db, tenant_id)
    needs = await reorder_needs(db, outlet_id, today)
    ids = {n.item_id for n in needs}
    offers = await _offers(db, ids, today)
    factors = await base_factors(db, {(i, o.pack_unit_id) for i, o in offers.items()})
    names = await item_names(db, tenant_id, language, ids)
    groups: dict[uuid.UUID | None, list[SuggestionLine]] = defaultdict(list)
    for n in needs:
        offer = offers.get(n.item_id)
        factor = factors.get((n.item_id, offer.pack_unit_id)) if offer else None
        label = (names[n.item_id].name, names[n.item_id].unit_code)
        groups[offer.vendor_id if offer else None].append(_line(n, offer, factor, label))
    vendors = dict(
        (
            await db.execute(
                select(Vendor.id, Vendor.name).where(Vendor.id.in_([v for v in groups if v]))
            )
        ).all()
    )
    out = [
        SuggestionGroup(
            vendor_id=v,
            vendor_name=vendors.get(v) if v else None,
            lines=sorted(ls, key=lambda x: x.name.lower()),
        )
        for v, ls in groups.items()
    ]
    return sorted(out, key=lambda g: (g.vendor_id is None, (g.vendor_name or "").lower()))
