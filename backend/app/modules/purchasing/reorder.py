"""Reorder suggestions (FR-INV-013): items at or below their reorder point at an outlet,
grouped by vendor, with quantities in the vendor's packs, ready to become a draft PO.

Vendor per item: the vendor item marked preferred, else the best-ranked vendor by price, lead
time and reliability (FR-PUR-007). Prices and packs are the latest from each vendor."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import base_factors, item_names, tenant_today
from app.modules.inventory.interface import Need, needs_with_eoq
from app.modules.purchasing import vendor_rank
from app.modules.purchasing.models import Vendor
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


async def _offers(
    db: AsyncSession, tenant_id: uuid.UUID, ids: set[uuid.UUID], today: date
) -> dict[uuid.UUID, Offer]:
    """The preferred vendor item, else the best-ranked vendor (FR-PUR-007)."""
    best: dict[uuid.UUID, Offer] = {}
    for item_id, ranked in (await vendor_rank.scores(db, tenant_id, ids, today)).items():
        pick = next((s for s in ranked if s.preferred), ranked[0])
        vi = pick.vendor_item
        best[item_id] = Offer(
            vi.vendor_id,
            vi.pack_qty,
            vi.pack_unit_id,
            vi.price,
            vi.min_order_qty,
            vi.is_preferred,
            pick.per_base,
        )
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
        eoq=need.eoq,
        order_qty=order_qty,
        order_unit_id=unit,
        unit_price=unit_price,
    )


async def suggestions(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, language: str
) -> list[SuggestionGroup]:
    today = await tenant_today(db, tenant_id)
    needs = await needs_with_eoq(db, outlet_id, today)
    ids = {n.item_id for n in needs}
    offers = await _offers(db, tenant_id, ids, today)
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
