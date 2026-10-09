"""Returns to vendors and their credit notes (FR-PUR-008).

Stock leaves at average cost through the inventory engine, in the same transaction (rule 3),
never below zero: you cannot send back what you do not have. The vendor then owes the credit
amount, by default the price paid on the receipt it came from; once the vendor's credit note
arrives it is recorded and can be applied to one of the vendor's bills."""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.modules.catalog.interface import base_factors, item_names
from app.modules.inventory.interface import OutLine, Posting, consume, reverse, visible_outlet
from app.modules.purchasing.ap_models import VendorReturn, VendorReturnLine
from app.modules.purchasing.ap_schemas import (
    BaseLine,
    CreditNoteIn,
    ReturnLineOut,
    VendorReturnIn,
    VendorReturnOut,
)
from app.modules.purchasing.models import GoodsReceipt, GoodsReceiptLine, Vendor

DOC_TYPE = "vendor_return"


async def _paid_prices(db: AsyncSession, receipt: GoodsReceipt | None) -> dict[uuid.UUID, Decimal]:
    """Price paid per base unit on the receipt, per item."""
    if receipt is None:
        return {}
    rows = list(
        await db.scalars(select(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id == receipt.id))
    )
    factors = await base_factors(db, {(r.item_id, r.unit_id) for r in rows})
    return {
        r.item_id: Decimal(r.line_total) / (r.qty * factors[(r.item_id, r.unit_id)]) for r in rows
    }


async def _receipt(db: AsyncSession, data: VendorReturnIn) -> GoodsReceipt | None:
    if data.receipt_id is None:
        return None
    receipt = await db.get(GoodsReceipt, data.receipt_id)
    if receipt is None or receipt.status != "posted":
        raise NotFoundError("receipt_not_found")
    if receipt.vendor_id != data.vendor_id or receipt.outlet_id != data.outlet_id:
        raise ConflictError("receipt_mismatch")
    return receipt


def _credit(given: int | None, paid: Decimal | None, qty: Decimal, cost: int) -> int:
    if given is not None:
        return given
    if paid is not None:
        return int((paid * qty).quantize(Decimal(1), ROUND_HALF_UP))
    return cost


async def post_return(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: VendorReturnIn
) -> VendorReturn:
    await visible_outlet(db, data.outlet_id)
    if await db.get(Vendor, data.vendor_id) is None:
        raise NotFoundError("vendor_not_found")
    prices = await _paid_prices(db, await _receipt(db, data))
    doc = VendorReturn(
        tenant_id=tenant_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC_TYPE, on=data.business_date
        ),
        outlet_id=data.outlet_id,
        vendor_id=data.vendor_id,
        receipt_id=data.receipt_id,
        business_date=data.business_date,
        reason=data.reason,
        note=data.note,
        stock_value=0,
        credit_amount=0,
        created_by=user_id,
    )
    db.add(doc)
    await db.flush()
    p = Posting(tenant_id, data.outlet_id, user_id, DOC_TYPE, doc.id, data.business_date)
    for ln in data.lines:
        row = VendorReturnLine(
            tenant_id=tenant_id,
            return_id=doc.id,
            item_id=ln.item_id,
            qty=ln.qty,
            batch_id=ln.batch_id,
            credit_amount=0,
        )
        db.add(row)
        await db.flush()
        out = OutLine(ln.item_id, ln.qty, ln.batch_id, row.id)
        moved = await consume(db, p, "vendor_return", [out], allow_negative=False)
        cost = -sum(m.value for m in moved.movements)
        row.credit_amount = _credit(ln.credit_amount, prices.get(ln.item_id), ln.qty, cost)
        doc.stock_value += cost
        doc.credit_amount += row.credit_amount
    await db.flush()
    await _audit(db, doc, user_id, "post", {"credit_amount": doc.credit_amount})
    return doc


async def _audit(
    db: AsyncSession, doc: VendorReturn, user_id: uuid.UUID, verb: str, extra: dict[str, object]
) -> None:
    await audit.record(
        db,
        tenant_id=doc.tenant_id,
        user_id=user_id,
        outlet_id=doc.outlet_id,
        action=f"purchasing.return.{verb}",
        target_type=DOC_TYPE,
        target_id=doc.id,
        summary={"number": doc.number, **extra},
    )


async def get_return(db: AsyncSession, return_id: uuid.UUID, *, lock: bool = False) -> VendorReturn:
    doc = await db.get(VendorReturn, return_id, with_for_update=lock)
    if doc is None:
        raise NotFoundError("return_not_found")
    return doc


async def reverse_return(
    db: AsyncSession, doc: VendorReturn, *, user_id: uuid.UUID, on: date
) -> VendorReturn:
    """Undo a return entered by mistake: the stock comes back; not once credited."""
    if doc.status != "posted":
        raise ConflictError("already_reversed")
    if doc.credit_note_number is not None:
        raise ConflictError("already_credited")
    p = Posting(doc.tenant_id, doc.outlet_id, user_id, DOC_TYPE, doc.id, on)
    await reverse(db, p, DOC_TYPE, doc.id)
    doc.status = "reversed"
    await db.flush()
    await _audit(db, doc, user_id, "reverse", {})
    return doc


async def record_credit_note(
    db: AsyncSession, doc: VendorReturn, *, user_id: uuid.UUID, data: CreditNoteIn
) -> VendorReturn:
    if doc.status != "posted":
        raise ConflictError("return_reversed")
    if doc.applied_bill_id is not None:
        raise ConflictError("credit_already_applied")
    doc.credit_note_number, doc.credited_on = data.credit_note_number, data.credited_on
    if data.credit_amount is not None:
        doc.credit_amount = data.credit_amount
    await db.flush()
    await _audit(
        db,
        doc,
        user_id,
        "credit_note",
        {"credit_note": doc.credit_note_number, "credit_amount": doc.credit_amount},
    )
    return doc


async def return_out(db: AsyncSession, doc: VendorReturn) -> VendorReturnOut:
    lines = await db.scalars(select(VendorReturnLine).where(VendorReturnLine.return_id == doc.id))
    return VendorReturnOut(
        **{k: getattr(doc, k) for k in VendorReturnOut.model_fields if k != "lines"},
        lines=[ReturnLineOut.model_validate(ln, from_attributes=True) for ln in lines],
    )


async def list_returns(
    db: AsyncSession, outlet_id: uuid.UUID, vendor_id: uuid.UUID | None = None
) -> list[VendorReturn]:
    stmt = select(VendorReturn).where(VendorReturn.outlet_id == outlet_id)
    if vendor_id:
        stmt = stmt.where(VendorReturn.vendor_id == vendor_id)
    stmt = stmt.order_by(VendorReturn.business_date.desc(), VendorReturn.created_at.desc())
    return list(await db.scalars(stmt.limit(100)))


async def receipt_base_lines(
    db: AsyncSession, tenant_id: uuid.UUID, receipt_id: uuid.UUID, language: str
) -> tuple[GoodsReceipt, list[BaseLine]]:
    receipt = await db.get(GoodsReceipt, receipt_id)
    if receipt is None:
        raise NotFoundError("receipt_not_found")
    rows = list(
        await db.scalars(select(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id == receipt.id))
    )
    factors = await base_factors(db, {(r.item_id, r.unit_id) for r in rows})
    names = await item_names(db, tenant_id, language, {r.item_id for r in rows})
    return receipt, [
        BaseLine(
            item_id=r.item_id,
            sku=names[r.item_id].sku,
            name=names[r.item_id].name,
            unit_code=names[r.item_id].unit_code,
            qty=(r.qty * factors[(r.item_id, r.unit_id)]).quantize(Decimal("0.0001")),
            amount=r.line_total,
        )
        for r in rows
    ]
