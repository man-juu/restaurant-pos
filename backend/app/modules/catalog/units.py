"""Batched unit conversion (FR-CAT-002): factors for many (item, unit) pairs in 3 queries,
so recipe checks and costing never run one query per line."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Item, ItemUnitConversion, Unit
from app.modules.catalog.service import NoConversion, platform_factor

Pair = tuple[uuid.UUID, uuid.UUID]  # (item_id, unit_id)


def _factor(
    pair: Pair,
    bases: dict[uuid.UUID, uuid.UUID],
    explicit: dict[Pair, Decimal],
    units: dict[uuid.UUID, Unit],
) -> Decimal | None:
    item_id, unit_id = pair
    base = bases.get(item_id)
    if base is None:
        return None
    if unit_id == base:
        return Decimal(1)
    if pair in explicit:
        return explicit[pair]
    if unit_id not in units or base not in units:
        return None  # unknown unit, or another tenant's (invisible under RLS)
    return platform_factor(units[unit_id], units[base])


async def base_factors(db: AsyncSession, pairs: set[Pair]) -> dict[Pair, Decimal]:
    """How many base units of the item one `unit` is, for every pair. Exact decimals."""
    item_ids = {i for i, _ in pairs}
    bases: dict[uuid.UUID, uuid.UUID] = dict(
        (await db.execute(select(Item.id, Item.base_unit_id).where(Item.id.in_(item_ids)))).all()
    )
    conversions = select(
        ItemUnitConversion.item_id, ItemUnitConversion.unit_id, ItemUnitConversion.factor_to_base
    ).where(ItemUnitConversion.item_id.in_(item_ids))
    explicit = {(i, u): f for i, u, f in (await db.execute(conversions)).all()}
    unit_ids = {u for _, u in pairs} | set(bases.values())
    units = {
        u.id: u for u in (await db.execute(select(Unit).where(Unit.id.in_(unit_ids)))).scalars()
    }
    found = {pair: _factor(pair, bases, explicit, units) for pair in pairs}
    if missing := sorted((str(i), str(u)) for (i, u), f in found.items() if f is None):
        raise NoConversion(details={"item_unit_pairs": missing})
    return {pair: f for pair, f in found.items() if f is not None}
