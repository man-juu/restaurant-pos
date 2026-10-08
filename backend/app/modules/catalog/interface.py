"""What other modules may use from the catalog (module boundaries, CLAUDE.md rule 4).

Modules that declare `depends_on=("catalog",)` import from here only, never catalog tables,
so the catalog can change its internals without breaking them.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.boms import ItemLabel, item_names
from app.modules.catalog.costing import CostSource, explode, recipe_needs, set_cost_source
from app.modules.catalog.models import Item, Unit
from app.modules.catalog.permissions import COST_VIEW
from app.modules.catalog.prices import tenant_today
from app.modules.catalog.units import base_factors

__all__ = [
    "COST_VIEW",
    "CostSource",
    "ItemLabel",
    "StockItem",
    "base_factors",
    "explode",
    "item_ids_by_sku",
    "item_names",
    "recipe_needs",
    "set_cost_source",
    "stock_items",
    "tenant_today",
    "unit_ids_by_code",
]


@dataclass(frozen=True)
class StockItem:
    id: uuid.UUID
    type: str
    base_unit_id: uuid.UUID
    is_stocked: bool
    is_active: bool
    shelf_life_days: int | None
    tracking_mode: str = "exact"
    storage_type: str | None = None
    allergens: tuple[str, ...] = ()

    @property
    def estimated(self) -> bool:
        """Hard-to-measure items never block a posting for lack of stock (owner, 0.26/0.27)."""
        return self.tracking_mode == "estimated"

    @property
    def perishable(self) -> bool:
        """FR-INV-003: items with a shelf life need an expiry date when they arrive."""
        return self.shelf_life_days is not None


async def stock_items(db: AsyncSession, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, StockItem]:
    """Items visible to the current tenant (RLS); unknown or foreign ids are simply absent."""
    stmt = select(
        Item.id,
        Item.type,
        Item.base_unit_id,
        Item.is_stocked,
        Item.is_active,
        Item.shelf_life_days,
        Item.tracking_mode,
        Item.storage_type,
        Item.allergens,
    ).where(Item.id.in_(set(ids)))
    rows = (await db.execute(stmt)).all()
    return {r.id: StockItem(*r[:-1], allergens=tuple(r.allergens or ())) for r in rows}


async def item_ids_by_sku(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Lower-cased SKU -> item id for the current tenant (imports)."""
    return {s.lower(): i for i, s in (await db.execute(select(Item.id, Item.sku))).all()}


async def unit_ids_by_code(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Lower-cased unit code -> unit id (platform and tenant units)."""
    return {c.lower(): i for i, c in (await db.execute(select(Unit.id, Unit.code))).all()}
