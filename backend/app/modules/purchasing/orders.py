"""Purchase orders (FR-PUR-003, 005, 006): draft -> submit (approval by amount, FR-TEN-007)
-> receive in one or more receipts. Every receipt posts stock through the shared receipt path;
differences against the order (quantity, price) are visible line by line."""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.approvals import (
    approvers_needed,
    ensure_may_decide,
    ensure_status,
    mark_decided,
    mark_submitted,
    request_approval,
)
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.modules.catalog.interface import base_factors, stock_items
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorLeadHistory,
)
from app.modules.purchasing.receipts import LineSpec, ReceiptHead, check_refs, post_receipt
from app.modules.purchasing.schemas import OrderIn, OrderLineOut, OrderOut, ReceiveIn

DOC = "purchase_order"
OPEN_FOR_RECEIPT = ("approved", "partially_received")


def _money(qty: Decimal, price: int) -> int:
    return int((qty * price).quantize(Decimal(1), ROUND_HALF_UP))


async def get_order(db: AsyncSession, po_id: uuid.UUID, *, lock: bool = False) -> PurchaseOrder:
    po = await db.get(PurchaseOrder, po_id, with_for_update=lock)
    if po is None:
        raise NotFoundError("order_not_found")
    return po


async def order_lines(db: AsyncSession, po_id: uuid.UUID) -> list[PurchaseOrderLine]:
    stmt = select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po_id)
    return list(await db.scalars(stmt.order_by(PurchaseOrderLine.id)))


async def order_out(db: AsyncSession, po: PurchaseOrder) -> OrderOut:
    lines = [
        OrderLineOut.model_validate(ln, from_attributes=True) for ln in await order_lines(db, po.id)
    ]
    fields = {k: getattr(po, k) for k in OrderOut.model_fields if k != "lines"}
    return OrderOut(**fields, lines=lines)


async def _audit(db: AsyncSession, po: PurchaseOrder, user_id: uuid.UUID, action: str) -> None:
    await audit.record(
        db,
        tenant_id=po.tenant_id,
        user_id=user_id,
        outlet_id=po.outlet_id,
        action=f"purchasing.order.{action}",
        target_type=DOC,
        target_id=po.id,
        summary={"number": po.number, "status": po.status, "total": po.total},
    )


async def save_order(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: OrderIn,
    po_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Create a draft or replace a draft's content."""
    await check_refs(db, tenant_id, data.outlet_id, data.vendor_id, None)
    ids = {ln.item_id for ln in data.lines}
    if missing := ids - (await stock_items(db, ids)).keys():
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, missing))})
    await base_factors(db, {(ln.item_id, ln.unit_id) for ln in data.lines})  # units must convert
    fields = data.model_dump(exclude={"lines"})
    if po_id is None:
        po = PurchaseOrder(tenant_id=tenant_id, created_by=user_id, **fields)
        db.add(po)
    else:
        po = await get_order(db, po_id, lock=True)
        ensure_status(po, "draft")
        for key, value in fields.items():
            setattr(po, key, value)
        await db.execute(delete(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id))
    po.total = sum(_money(ln.qty, ln.unit_price) for ln in data.lines)
    await db.flush()
    await db.execute(
        insert(PurchaseOrderLine),
        [{"tenant_id": tenant_id, "po_id": po.id, **ln.model_dump()} for ln in data.lines],
    )
    await _audit(db, po, user_id, "save")
    return po


async def submit(db: AsyncSession, *, user_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    po = await get_order(db, po_id, lock=True)
    ensure_status(po, "draft")
    po.number = await settings.allocate_number(
        db, tenant_id=po.tenant_id, doc_type=DOC, on=po.order_date
    )
    if await request_approval(db, DOC, po, po.total, number=po.number, link="/purchasing"):
        mark_submitted(po)
    else:  # no rule for this amount: approved at once (tenant setting decides)
        mark_submitted(po)
        mark_decided(po, "approved", user_id)
    await _audit(db, po, user_id, "submit")
    return po


async def decide(
    db: AsyncSession, *, user_id: uuid.UUID, role_id: uuid.UUID, po_id: uuid.UUID, approve: bool
) -> PurchaseOrder:
    po = await get_order(db, po_id, lock=True)
    ensure_status(po, "submitted")
    roles = await approvers_needed(db, DOC, po, po.total)
    await ensure_may_decide(db, po, roles, user_id=user_id, role_id=role_id)
    mark_decided(po, "approved" if approve else "rejected", user_id)
    await _audit(db, po, user_id, "approve" if approve else "reject")
    return po


async def cancel(db: AsyncSession, *, user_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    po = await get_order(db, po_id, lock=True)
    ensure_status(po, "draft", "submitted", "approved")  # not once anything arrived
    po.status = "cancelled"
    await _audit(db, po, user_id, "cancel")
    return po


def _status_after(lines: list[PurchaseOrderLine]) -> str:
    if all(ln.received_qty >= ln.qty for ln in lines):
        return "received"
    return "partially_received" if any(ln.received_qty > 0 for ln in lines) else "approved"


async def receive(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, po_id: uuid.UUID, data: ReceiveIn
) -> GoodsReceipt:
    po = await get_order(db, po_id, lock=True)
    ensure_status(po, *OPEN_FOR_RECEIPT)
    await check_refs(db, tenant_id, po.outlet_id, po.vendor_id, data.invoice_upload_id)
    lines = {ln.id: ln for ln in await order_lines(db, po.id)}
    specs = []
    for rl in data.lines:
        ordered = lines.get(rl.po_line_id)
        if ordered is None:
            raise NotFoundError("order_line_not_found")
        if ordered.received_qty + rl.qty > ordered.qty:
            raise ConflictError("more_than_ordered", details={"po_line_id": str(ordered.id)})
        ordered.received_qty += rl.qty
        price = ordered.unit_price if rl.unit_price is None else rl.unit_price
        specs.append(
            LineSpec(
                ordered.item_id,
                rl.qty,
                ordered.unit_id,
                _money(rl.qty, price),
                rl.lot_code,
                rl.expiry_date,
                ordered.id,
            )
        )
    head = ReceiptHead(
        outlet_id=po.outlet_id,
        business_date=data.business_date,
        vendor_id=po.vendor_id,
        po_id=po.id,
        invoice_upload_id=data.invoice_upload_id,
        note=data.note,
    )
    receipt = await post_receipt(db, tenant_id=tenant_id, user_id=user_id, head=head, lines=specs)
    await db.execute(
        insert(VendorLeadHistory),
        [
            {
                "tenant_id": tenant_id,
                "vendor_id": po.vendor_id,
                "item_id": s.item_id,
                "ordered_at": po.order_date,
                "received_at": data.business_date,
                "source_doc_id": receipt.id,
            }
            for s in specs
        ],
    )
    po.status = _status_after(list(lines.values()))
    await _audit(db, po, user_id, "receive")
    return receipt


async def undo_receipt_quantities(db: AsyncSession, receipt: GoodsReceipt) -> None:
    """A reversed receipt gives its quantities back to the order lines."""
    po = await get_order(db, receipt.po_id, lock=True) if receipt.po_id else None
    if po is None:
        return
    lines = {ln.id: ln for ln in await order_lines(db, po.id)}
    received = await db.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id == receipt.id)
    )
    for rl in received:
        if rl.po_line_id in lines:
            lines[rl.po_line_id].received_qty -= rl.qty
    po.status = _status_after(list(lines.values()))
