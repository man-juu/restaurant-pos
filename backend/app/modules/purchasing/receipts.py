"""Goods receipts (FR-PUR-004, 005, 006, 011). Part 1: quick purchase, a market or cash buy
received in one step. Stock posts through the inventory engine in the same transaction; the
price paid per base unit goes to price history and moves the average cost."""

import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.schemas import PurchasingSettings
from app.core.uploads.models import Upload
from app.modules.catalog.interface import StockItem, base_factors, stock_items
from app.modules.inventory.interface import InLine, Posting, receive, reverse, visible_outlet
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Vendor,
    VendorPriceHistory,
)
from app.modules.purchasing.schemas import QuickLineIn, QuickPurchaseIn, ReceiptLineOut, ReceiptOut

DOC_TYPE = "goods_receipt"
QTY = Decimal("0.0001")
COST = Decimal("0.000001")


class InvoiceRequired(AppError):
    status_code, code = 422, "invoice_required"


async def _check_refs(db: AsyncSession, tenant_id: uuid.UUID, data: QuickPurchaseIn) -> None:
    await visible_outlet(db, data.outlet_id)
    if data.vendor_id and await db.get(Vendor, data.vendor_id) is None:
        raise NotFoundError("vendor_not_found")
    if data.invoice_upload_id:
        upload = await db.get(Upload, data.invoice_upload_id)  # RLS: own tenant only
        if upload is None or upload.purpose != "invoice":
            raise NotFoundError("upload_not_found")
    rules = cast(PurchasingSettings, await settings.get_setting(db, tenant_id, "purchasing"))
    if rules.require_invoice_attachment and not data.invoice_upload_id:
        raise InvoiceRequired()


def _expiry(line: QuickLineIn, item: StockItem, data: QuickPurchaseIn) -> QuickLineIn:
    """Owner decision 0.27: a missing expiry date is filled from the item's shelf life."""
    if line.expiry_date is None and item.shelf_life_days:
        return line.model_copy(
            update={"expiry_date": data.business_date + timedelta(days=item.shelf_life_days)}
        )
    return line


async def quick_purchase(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: QuickPurchaseIn
) -> GoodsReceipt:
    await _check_refs(db, tenant_id, data)
    items = await stock_items(db, {ln.item_id for ln in data.lines})
    lines = [
        _expiry(ln, items[ln.item_id], data) if ln.item_id in items else ln for ln in data.lines
    ]
    factors = await base_factors(db, {(ln.item_id, ln.unit_id) for ln in lines})
    receipt = GoodsReceipt(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        vendor_id=data.vendor_id,
        vendor_name=data.vendor_name,
        business_date=data.business_date,
        total=sum(ln.line_total for ln in lines),
        invoice_upload_id=data.invoice_upload_id,
        note=data.note,
        created_by=user_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC_TYPE, on=data.business_date
        ),
    )
    db.add(receipt)
    await db.flush()
    rows = [
        GoodsReceiptLine(tenant_id=tenant_id, receipt_id=receipt.id, **ln.model_dump())
        for ln in lines
    ]
    db.add_all(rows)
    await db.flush()
    stock_lines, history = [], []
    for row in rows:
        base_qty = (row.qty * factors[(row.item_id, row.unit_id)]).quantize(QTY, ROUND_HALF_UP)
        if base_qty <= 0:
            raise ConflictError("quantity_too_small", details={"item_id": str(row.item_id)})
        unit_cost = (Decimal(row.line_total) / base_qty).quantize(COST, ROUND_HALF_UP)
        stock_lines.append(
            InLine(row.item_id, base_qty, unit_cost, row.lot_code, row.expiry_date, row.id)
        )
        history.append(
            {
                "tenant_id": tenant_id,
                "vendor_id": data.vendor_id,
                "item_id": row.item_id,
                "unit_cost": unit_cost,
                "observed_at": data.business_date,
                "source_doc_id": receipt.id,
            }
        )
    p = Posting(tenant_id, data.outlet_id, user_id, DOC_TYPE, receipt.id, data.business_date)
    await receive(db, p, "purchase_receipt", stock_lines)
    await db.execute(insert(VendorPriceHistory), history)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=data.outlet_id,
        action="purchasing.quick_purchase",
        target_type=DOC_TYPE,
        target_id=receipt.id,
        summary={"number": receipt.number, "total": receipt.total, "lines": len(rows)},
    )
    return receipt


async def reverse_receipt(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID
) -> GoodsReceipt:
    """FR-X-005: undo by reversal; only while the received batches still hold the stock."""
    receipt = await db.get(GoodsReceipt, receipt_id, with_for_update=True)
    if receipt is None:
        raise NotFoundError("receipt_not_found")
    if receipt.status != "posted":
        raise ConflictError("already_reversed")
    p = Posting(
        receipt.tenant_id, receipt.outlet_id, user_id, DOC_TYPE, receipt.id, receipt.business_date
    )
    await reverse(db, p, DOC_TYPE, receipt.id)
    receipt.status = "reversed"
    await audit.record(
        db,
        tenant_id=receipt.tenant_id,
        user_id=user_id,
        outlet_id=receipt.outlet_id,
        action="purchasing.receipt.reverse",
        target_type=DOC_TYPE,
        target_id=receipt.id,
        summary={"number": receipt.number},
    )
    return receipt


async def receipt_out(db: AsyncSession, receipt: GoodsReceipt) -> ReceiptOut:
    lines = await db.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id == receipt.id)
    )
    return ReceiptOut(
        **{k: getattr(receipt, k) for k in ReceiptOut.model_fields if k != "lines"},
        lines=[ReceiptLineOut.model_validate(ln, from_attributes=True) for ln in lines],
    )


async def list_receipts(
    db: AsyncSession, outlet_id: uuid.UUID, limit: int = 100
) -> list[GoodsReceipt]:
    stmt = (
        select(GoodsReceipt)
        .where(GoodsReceipt.outlet_id == outlet_id)
        .order_by(GoodsReceipt.business_date.desc(), GoodsReceipt.created_at.desc())
        .limit(limit)
    )
    return list(await db.scalars(stmt))
