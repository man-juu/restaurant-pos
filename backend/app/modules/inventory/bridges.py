"""Helpers other modules use through `interface.py`: batch details for documents that move
batches (transfers), and a loss adjustment that goes through the normal approval flow."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import stock_items
from app.modules.inventory import documents
from app.modules.inventory.doc_models import Adjustment
from app.modules.inventory.doc_schemas import AdjustmentIn, AdjustmentLineIn
from app.modules.inventory.models import StockBatch


@dataclass(frozen=True)
class BatchInfo:
    lot_code: str | None
    expiry_date: date | None


async def batch_details(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, BatchInfo]:
    stmt = select(StockBatch.id, StockBatch.lot_code, StockBatch.expiry_date).where(
        StockBatch.id.in_(ids)
    )
    return {i: BatchInfo(lot, exp) for i, lot, exp in (await db.execute(stmt)).all()}


async def loss_adjustment(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    outlet_id: uuid.UUID,
    business_date: date,
    losses: dict[uuid.UUID, Decimal],  # base quantity to take out, per item
    note: str,
) -> Adjustment:
    """FR-TRF-003: a discrepancy becomes a submitted adjustment; the tenant's approval
    rules decide whether it posts at once or waits for an approver."""
    items = await stock_items(db, losses.keys())
    data = AdjustmentIn(
        outlet_id=outlet_id,
        business_date=business_date,
        reason_code="damaged",
        note=note[:500],
        lines=[
            AdjustmentLineIn(item_id=i, qty=-q, unit_id=items[i].base_unit_id)
            for i, q in losses.items()
        ],
    )
    adj = await documents.save_adjustment(db, tenant_id=tenant_id, user_id=user_id, data=data)
    return await documents.submit_adjustment(db, user_id=user_id, adjustment_id=adj.id)
