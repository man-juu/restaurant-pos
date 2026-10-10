"""Vendor bills, payments and credits (FR-PUR-009, 008).

A bill is the vendor's invoice for receipts (and usually a PO). It is matched three ways on
entry (bill_match.py), falls due after the vendor's payment terms, and is settled by payments
and by applying the vendor's credit notes. Payments are append-only; a mistake is reversed."""

import uuid
from datetime import date, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.schemas import PaymentMethodSettings, PurchasingSettings
from app.modules.inventory.interface import visible_outlet
from app.modules.purchasing import bill_match, events
from app.modules.purchasing.ap_models import (
    VendorBill,
    VendorBillLine,
    VendorBillReceipt,
    VendorPayment,
    VendorReturn,
)
from app.modules.purchasing.ap_schemas import (
    BillLineOut,
    MatchNote,
    PayableRow,
    PaymentIn,
    PaymentOut,
    VendorBillIn,
    VendorBillOut,
)
from app.modules.purchasing.models import GoodsReceipt, PurchaseOrder, Vendor

DOC_TYPE = "vendor_bill"


async def _audit(
    db: AsyncSession, bill: VendorBill, user_id: uuid.UUID, verb: str, extra: dict[str, object]
) -> None:
    await audit.record(
        db,
        tenant_id=bill.tenant_id,
        user_id=user_id,
        outlet_id=bill.outlet_id,
        action=f"purchasing.bill.{verb}",
        target_type=DOC_TYPE,
        target_id=bill.id,
        summary={"number": bill.number, **extra},
    )


async def _receipts(db: AsyncSession, data: VendorBillIn) -> list[uuid.UUID]:
    """The receipts this bill covers: those named, or else every unbilled one of the PO."""
    ids = list(dict.fromkeys(data.receipt_ids))
    if not ids and data.po_id:
        stmt = select(GoodsReceipt.id).where(
            GoodsReceipt.po_id == data.po_id,
            GoodsReceipt.status == "posted",
            GoodsReceipt.outlet_id == data.outlet_id,
        )
        ids = [i for i in await db.scalars(stmt) if not await _billed(db, i)]
    for rid in ids:
        r = await db.get(GoodsReceipt, rid)
        # Only this outlet's receipts: a user scoped to one outlet cannot claim another's.
        if (
            r is None
            or r.status != "posted"
            or r.vendor_id != data.vendor_id
            or r.outlet_id != data.outlet_id
        ):
            raise NotFoundError("receipt_not_found", details={"receipt_id": str(rid)})
        if await _billed(db, rid):
            raise ConflictError("receipt_already_billed", details={"receipt_id": str(rid)})
    return ids


async def _billed(db: AsyncSession, receipt_id: uuid.UUID) -> bool:
    stmt = (
        select(VendorBill.id)
        .join(VendorBillReceipt, VendorBillReceipt.bill_id == VendorBill.id)
        .where(VendorBillReceipt.receipt_id == receipt_id, VendorBill.status != "void")
    )
    return await db.scalar(stmt.limit(1)) is not None


async def _check(db: AsyncSession, data: VendorBillIn) -> Vendor:
    await visible_outlet(db, data.outlet_id)
    vendor = await db.get(Vendor, data.vendor_id)
    if vendor is None:
        raise NotFoundError("vendor_not_found")
    if data.po_id:
        po = await db.get(PurchaseOrder, data.po_id)
        if po is None or po.vendor_id != data.vendor_id:
            raise NotFoundError("order_not_found")
    dup = select(VendorBill.id).where(
        VendorBill.vendor_id == data.vendor_id,
        VendorBill.vendor_invoice_no == data.vendor_invoice_no,
    )
    if await db.scalar(dup) is not None:
        raise ConflictError("duplicate_vendor_invoice")
    return vendor


async def create_bill(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: VendorBillIn
) -> VendorBill:
    vendor = await _check(db, data)
    receipt_ids = await _receipts(db, data)
    rules = cast(PurchasingSettings, await settings.get_setting(db, tenant_id, "purchasing"))
    po_prices = await bill_match.ordered(db, data.po_id) if data.po_id else None
    got = await bill_match.received(db, receipt_ids)
    status, notes = bill_match.match(data.lines, po_prices, got, rules.bill_price_tolerance_bp)
    bill = VendorBill(
        tenant_id=tenant_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC_TYPE, on=data.bill_date
        ),
        vendor_id=data.vendor_id,
        vendor_invoice_no=data.vendor_invoice_no,
        outlet_id=data.outlet_id,
        po_id=data.po_id,
        bill_date=data.bill_date,
        due_date=data.due_date or data.bill_date + timedelta(days=vendor.payment_terms_days),
        total=sum(ln.amount for ln in data.lines),
        match_status=status,
        match_notes=[n.model_dump(mode="json") for n in notes],
        note=data.note,
        created_by=user_id,
    )
    db.add(bill)
    await db.flush()
    db.add_all(
        VendorBillLine(tenant_id=tenant_id, bill_id=bill.id, **ln.model_dump()) for ln in data.lines
    )
    db.add_all(
        VendorBillReceipt(tenant_id=tenant_id, bill_id=bill.id, receipt_id=r) for r in receipt_ids
    )
    await db.flush()
    await _audit(db, bill, user_id, "create", {"total": bill.total, "match": status})
    return bill


async def get_bill(db: AsyncSession, bill_id: uuid.UUID, *, lock: bool = False) -> VendorBill:
    bill = await db.get(VendorBill, bill_id, with_for_update=lock)
    if bill is None:
        raise NotFoundError("bill_not_found")
    return bill


def _settle(bill: VendorBill) -> None:
    if bill.status == "void":
        return
    settled = bill.paid + bill.credited
    bill.status = "paid" if settled >= bill.total else "partially_paid" if settled else "open"


def balance(bill: VendorBill) -> int:
    return 0 if bill.status == "void" else bill.total - bill.paid - bill.credited


async def pay(
    db: AsyncSession, bill: VendorBill, *, user_id: uuid.UUID, data: PaymentIn
) -> VendorPayment:
    if bill.status in ("void", "paid"):
        raise ConflictError("bill_not_open", details={"status": bill.status})
    rules = cast(PurchasingSettings, await settings.get_setting(db, bill.tenant_id, "purchasing"))
    if rules.block_mismatched_payment and bill.match_status == "mismatch":
        raise ConflictError("bill_mismatch")
    methods = cast(
        PaymentMethodSettings, await settings.get_setting(db, bill.tenant_id, "payment_methods")
    )
    kinds = {m.code: m.kind for m in methods.methods if m.active}
    if data.method not in kinds:
        raise NotFoundError("payment_method_not_found")
    if data.amount > balance(bill):
        raise ConflictError("payment_exceeds_balance", details={"balance": balance(bill)})
    row = VendorPayment(
        tenant_id=bill.tenant_id, bill_id=bill.id, created_by=user_id, **data.model_dump()
    )
    db.add(row)
    bill.paid += data.amount
    _settle(bill)
    await db.flush()
    await _audit(db, bill, user_id, "pay", {"amount": data.amount, "method": data.method})
    await events.bill_paid(
        db,
        tenant_id=bill.tenant_id,
        user_id=user_id,
        bill_id=bill.id,
        outlet_id=bill.outlet_id,
        day=data.paid_on,
        amount=data.amount,
        method_kind=kinds[data.method],
    )
    return row


async def reverse_payment(
    db: AsyncSession, bill: VendorBill, payment_id: uuid.UUID, *, user_id: uuid.UUID, on: date
) -> VendorPayment:
    original = await db.get(VendorPayment, payment_id)
    if original is None or original.bill_id != bill.id or original.amount < 0:
        raise NotFoundError("payment_not_found")
    undone = select(VendorPayment.id).where(VendorPayment.reverses_id == original.id)
    if await db.scalar(undone) is not None:
        raise ConflictError("already_reversed")
    row = VendorPayment(
        tenant_id=bill.tenant_id,
        bill_id=bill.id,
        paid_on=on,
        amount=-original.amount,
        method=original.method,
        reference=original.reference,
        reverses_id=original.id,
        created_by=user_id,
    )
    db.add(row)
    bill.paid -= original.amount
    _settle(bill)
    await db.flush()
    await _audit(db, bill, user_id, "reverse_payment", {"amount": original.amount})
    await events.bill_paid(
        db,
        tenant_id=bill.tenant_id,
        user_id=user_id,
        bill_id=bill.id,
        outlet_id=bill.outlet_id,
        day=on,
        amount=-original.amount,
        method_kind=await _kind_of(db, bill.tenant_id, original.method),
    )
    return row


async def _kind_of(db: AsyncSession, tenant_id: uuid.UUID, code: str) -> str:
    methods = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    return next((m.kind for m in methods.methods if m.code == code), "cash")


async def apply_credit(
    db: AsyncSession, bill: VendorBill, return_id: uuid.UUID, *, user_id: uuid.UUID
) -> VendorBill:
    """FR-PUR-008: the vendor's credit note for a return reduces what this bill still owes."""
    credit = await db.get(VendorReturn, return_id, with_for_update=True)
    # Same vendor and same outlet: one outlet cannot spend another outlet's credit.
    if (
        credit is None
        or credit.vendor_id != bill.vendor_id
        or credit.outlet_id != bill.outlet_id
        or credit.status != "posted"
    ):
        raise NotFoundError("return_not_found")
    if credit.credit_note_number is None:
        raise ConflictError("credit_note_missing")
    if credit.applied_bill_id is not None:
        raise ConflictError("credit_already_applied")
    if bill.status in ("void", "paid") or credit.credit_amount > balance(bill):
        raise ConflictError("credit_exceeds_balance", details={"balance": balance(bill)})
    credit.applied_bill_id = bill.id
    bill.credited += credit.credit_amount
    _settle(bill)
    await db.flush()
    await _audit(
        db, bill, user_id, "apply_credit", {"return": credit.number, "amount": credit.credit_amount}
    )
    return bill


async def void_bill(db: AsyncSession, bill: VendorBill, *, user_id: uuid.UUID) -> VendorBill:
    """A bill entered by mistake: only before anything was paid or credited against it."""
    if bill.status == "void":
        raise ConflictError("already_void")
    if bill.paid or bill.credited:
        raise ConflictError("bill_has_settlements")
    bill.status = "void"
    await db.flush()
    await _audit(db, bill, user_id, "void", {})
    return bill


async def bill_out(db: AsyncSession, bill: VendorBill) -> VendorBillOut:
    lines = await db.scalars(select(VendorBillLine).where(VendorBillLine.bill_id == bill.id))
    receipts = await db.scalars(
        select(VendorBillReceipt.receipt_id).where(VendorBillReceipt.bill_id == bill.id)
    )
    pays = await db.scalars(
        select(VendorPayment)
        .where(VendorPayment.bill_id == bill.id)
        .order_by(VendorPayment.created_at)
    )
    return VendorBillOut(
        **{
            k: getattr(bill, k)
            for k in VendorBillOut.model_fields
            if k not in ("lines", "payments", "receipt_ids", "balance", "match_notes")
        },
        balance=balance(bill),
        match_notes=[MatchNote.model_validate(n) for n in bill.match_notes],
        receipt_ids=list(receipts),
        lines=[BillLineOut.model_validate(ln, from_attributes=True) for ln in lines],
        payments=[PaymentOut.model_validate(p, from_attributes=True) for p in pays],
    )


async def list_bills(
    db: AsyncSession, outlet_id: uuid.UUID, status: str | None = None
) -> list[VendorBill]:
    stmt = select(VendorBill).where(VendorBill.outlet_id == outlet_id)
    if status:
        stmt = stmt.where(VendorBill.status == status)
    stmt = stmt.order_by(VendorBill.due_date, VendorBill.created_at)
    return list(await db.scalars(stmt.limit(200)))


async def payables(
    db: AsyncSession, outlet_ids: set[uuid.UUID] | None, today: date
) -> list[PayableRow]:
    """FR-PUR-009: unpaid bills, most overdue first (accounts payable aging)."""
    stmt = select(VendorBill).where(VendorBill.status.in_(("open", "partially_paid")))
    if outlet_ids is not None:
        stmt = stmt.where(VendorBill.outlet_id.in_(outlet_ids))
    rows = await db.scalars(stmt.order_by(VendorBill.due_date).limit(500))
    return [
        PayableRow(
            bill_id=b.id,
            number=b.number,
            vendor_id=b.vendor_id,
            vendor_invoice_no=b.vendor_invoice_no,
            due_date=b.due_date,
            balance=balance(b),
            days_overdue=max((today - b.due_date).days, 0),
        )
        for b in rows
    ]
