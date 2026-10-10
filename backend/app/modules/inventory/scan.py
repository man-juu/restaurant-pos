"""Scanning (FR-INV-019): a code from a label or a pack names a batch or an item. Batch labels
carry "B:<batch id>"; a plain code is tried as a lot code at the outlet, then as the pack's
barcode or the SKU."""

import uuid
from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.catalog.interface import item_by_code, item_names, stock_items
from app.modules.inventory.models import StockBatch

BATCH_PREFIX = "B:"


class ScanOut(BaseModel):
    kind: str  # "batch" or "item"
    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str
    base_unit_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    lot_code: str | None = None
    expiry_date: date | None = None


def batch_code(batch_id: uuid.UUID) -> str:
    return f"{BATCH_PREFIX}{batch_id}"


async def _batch(db: AsyncSession, outlet_id: uuid.UUID, code: str) -> StockBatch | None:
    if code.startswith(BATCH_PREFIX):
        try:
            batch_id = uuid.UUID(code[len(BATCH_PREFIX) :])
        except ValueError:
            return None
        return await db.scalar(
            select(StockBatch).where(StockBatch.id == batch_id, StockBatch.outlet_id == outlet_id)
        )
    return await db.scalar(
        select(StockBatch)
        .where(StockBatch.outlet_id == outlet_id, StockBatch.lot_code == code)
        .order_by(StockBatch.received_at.desc())
        .limit(1)
    )


async def resolve(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, code: str, language: str
) -> ScanOut:
    code = code.strip()
    batch = await _batch(db, outlet_id, code)
    item_id = batch.item_id if batch else await item_by_code(db, code)
    if item_id is None:
        raise NotFoundError("code_not_found")
    label = (await item_names(db, tenant_id, language, [item_id]))[item_id]
    item = (await stock_items(db, [item_id]))[item_id]
    return ScanOut(
        kind="batch" if batch else "item",
        item_id=item_id,
        sku=label.sku,
        name=label.name,
        unit_code=label.unit_code,
        base_unit_id=item.base_unit_id,
        batch_id=batch.id if batch else None,
        lot_code=batch.lot_code if batch else None,
        expiry_date=batch.expiry_date if batch else None,
    )
