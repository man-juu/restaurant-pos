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
from app.modules.catalog.costing import CostSource, explode, set_cost_source
from app.modules.catalog.models import Item
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
    "item_names",
    "set_cost_source",
    "stock_items",
    "tenant_today",
]


@dataclass(frozen=True)
class StockItem:
    id: uuid.UUID
    type: str
    base_unit_id: uuid.UUID
    is_stocked: bool
    is_active: bool
    shelf_life_days: int | None

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
    ).where(Item.id.in_(set(ids)))
    return {row.id: StockItem(*row) for row in (await db.execute(stmt)).all()}
