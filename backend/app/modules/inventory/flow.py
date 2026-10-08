"""Shared steps of stock documents: numbering, quantities in base units, value for approval
rules, and the submit/approve/reject flow (FR-TEN-007, docs/03 sections 6 and 7)."""

import uuid
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.approvals import (
    FlowDoc,
    approvers_needed,
    ensure_may_decide,
    ensure_status,
    mark_decided,
    mark_submitted,
)
from app.core.settings.service import allocate_number
from app.modules.catalog.interface import base_factors
from app.modules.inventory.models import ItemCost
from app.modules.inventory.service import money

# Re-exported for the inventory documents (the flow itself lives in app.core.approvals).
__all__ = [
    "FlowDoc",
    "approvers_needed",
    "average_costs",
    "ensure_may_decide",
    "ensure_status",
    "mark_decided",
    "mark_submitted",
    "next_number",
    "to_base",
    "value_of",
]

QTY = Decimal("0.0001")


async def next_number(db: AsyncSession, tenant_id: uuid.UUID, doc_type: str, doc: object) -> str:
    return await allocate_number(
        db,
        tenant_id=tenant_id,
        doc_type=doc_type,
        on=getattr(doc, "business_date"),  # noqa: B009 - every header has it
        outlet_id=getattr(doc, "outlet_id"),  # noqa: B009
    )


async def to_base(
    db: AsyncSession, lines: Iterable[tuple[uuid.UUID, uuid.UUID, Decimal]]
) -> dict[uuid.UUID, Decimal]:
    """(item, unit, qty) -> item: qty in the item's base unit (exact, 4 decimals)."""
    rows = list(lines)
    factors = await base_factors(db, {(i, u) for i, u, _ in rows})
    return {i: (q * factors[(i, u)]).quantize(QTY, rounding=ROUND_HALF_UP) for i, u, q in rows}


async def average_costs(
    db: AsyncSession, outlet_id: uuid.UUID, items: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    stmt = select(ItemCost.item_id, ItemCost.avg_cost).where(
        ItemCost.outlet_id == outlet_id, ItemCost.item_id.in_(set(items))
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def value_of(db: AsyncSession, outlet_id: uuid.UUID, qty: dict[uuid.UUID, Decimal]) -> int:
    """Approval amount: what the stock change is worth at today's average, ignoring sign."""
    costs = await average_costs(db, outlet_id, qty)
    return sum(money(abs(q), costs.get(i, Decimal(0))) for i, q in qty.items())
