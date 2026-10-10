"""Goods receipts (FR-PUR-004, 005, 006, 011). Part 1: quick purchase, a market or cash buy
received in one step. Stock posts through the inventory engine in the same transaction; the
price paid per base unit goes to price history and moves the average cost."""

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
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
from app.modules.purchasing import events
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Vendor,
    VendorPriceHistory,
)
from app.modules.purchasing.schemas import QuickPurchaseIn, ReceiptLineOut, ReceiptOut

DOC_TYPE = "goods_receipt"
QTY = Decimal("0.0001")
COST = Decimal("0.000001")


class InvoiceRequired(AppError):
    status_code, code = 422, "invoice_required"


async def check_refs(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    outlet_id: uuid.UUID,
    vendor_id: uuid.UUID | None,
    invoice_upload_id: uuid.UUID | None,
) -> None:
    await visible_outlet(db, outlet_id)
    if vendor_id and await db.get(Vendor, vendor_id) is None:
        raise NotFoundError("vendor_not_found")
    if invoice_upload_id:
        upload = await db.get(Upload, invoice_upload_id)  # RLS: own tenant only
        if upload is None or upload.purpose != "invoice":
            raise NotFoundError("upload_not_found")
    rules = cast(PurchasingSettings, await settings.get_setting(db, tenant_id, "purchasing"))
    if rules.require_invoice_attachment and not invoice_upload_id:
        raise InvoiceRequired()


@dataclass(frozen=True)
class LineSpec:
    """One received line, whatever the source (quick purchase or purchase order)."""

    item_id: uuid.UUID
    qty: Decimal
    unit_id: uuid.UUID
    line_total: int
    lot_code: str | None = None
    expiry_date: date | None = None
    po_line_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ReceiptHead:
    outlet_id: uuid.UUID
    business_date: date
    vendor_id: uuid.UUID | None = None
    vendor_name: str | None = None
    po_id: uuid.UUID | None = None
    invoice_upload_id: uuid.UUID | None = None
    note: str | None = None


def _filled(ln: LineSpec, items: dict[uuid.UUID, StockItem], day: date) -> LineSpec:
    """Owner decision 0.27: a missing expiry date is filled from the item's shelf life."""
    item = items.get(ln.item_id)
    if ln.expiry_date is None and item is not None and item.shelf_life_days:
        return replace(ln, expiry_date=day + timedelta(days=item.shelf_life_days))
    return ln


def _stock_line(row: GoodsReceiptLine, factor: Decimal) -> InLine:
    base_qty = (row.qty * factor).quantize(QTY, ROUND_HALF_UP)
    if base_qty <= 0:
        raise ConflictError("quantity_too_small", details={"item_id": str(row.item_id)})
    unit_cost = (Decimal(row.line_total) / base_qty).quantize(COST, ROUND_HALF_UP)
    return InLine(row.item_id, base_qty, unit_cost, row.lot_code, row.expiry_date, row.id)


async def post_receipt(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    head: ReceiptHead,
    lines: list[LineSpec],
) -> GoodsReceipt:
    """Write the receipt and post its stock in the caller's transaction (one writer)."""
    items = await stock_items(db, {ln.item_id for ln in lines})
    lines = [_filled(ln, items, head.business_date) for ln in lines]
    factors = await base_factors(db, {(ln.item_id, ln.unit_id) for ln in lines})
    receipt = GoodsReceipt(
        tenant_id=tenant_id,
        **asdict(head),
        total=sum(ln.line_total for ln in lines),
        created_by=user_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC_TYPE, on=head.business_date
        ),
    )
    db.add(receipt)
    await db.flush()
    rows = [
        GoodsReceiptLine(tenant_id=tenant_id, receipt_id=receipt.id, **asdict(ln)) for ln in lines
    ]
    db.add_all(rows)
    await db.flush()
    stock = [_stock_line(row, factors[(row.item_id, row.unit_id)]) for row in rows]
    p = Posting(tenant_id, head.outlet_id, user_id, DOC_TYPE, receipt.id, head.business_date)
    await receive(db, p, "purchase_receipt", stock)
    await db.execute(
        insert(VendorPriceHistory),
        [
            {
                "tenant_id": tenant_id,
                "vendor_id": head.vendor_id,
                "item_id": ln.item_id,
                "unit_cost": ln.unit_cost,
                "observed_at": head.business_date,
                "source_doc_id": receipt.id,
            }
            for ln in stock
        ],
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=head.outlet_id,
        action="purchasing.receipt.post",
        target_type=DOC_TYPE,
        target_id=receipt.id,
        summary={
            "number": receipt.number,
            "total": receipt.total,
            "po_id": str(head.po_id) if head.po_id else None,
        },
    )
    await events.receipt(db, events.RECEIPT_POSTED, receipt, user_id)
    return receipt


async def quick_purchase(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: QuickPurchaseIn
) -> GoodsReceipt:
    await check_refs(db, tenant_id, data.outlet_id, data.vendor_id, data.invoice_upload_id)
    head = ReceiptHead(
        outlet_id=data.outlet_id,
        business_date=data.business_date,
        vendor_id=data.vendor_id,
        vendor_name=data.vendor_name,
        invoice_upload_id=data.invoice_upload_id,
        note=data.note,
    )
    lines = [LineSpec(**ln.model_dump()) for ln in data.lines]
    return await post_receipt(db, tenant_id=tenant_id, user_id=user_id, head=head, lines=lines)


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
    await events.receipt(db, events.RECEIPT_REVERSED, receipt, user_id)
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
