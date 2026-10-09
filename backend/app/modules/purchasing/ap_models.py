"""Accounts payable tables (docs/05 section 2.4, FR-PUR-008, 009): returns to vendors with
their credit notes, vendor bills matched against the PO and receipts, and bill payments.
Money is integer minor units; quantities are in the item's base unit."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

RETURN_REASONS = ("damaged", "expired", "wrong_item", "quality", "other")
RETURN_STATUSES = ("posted", "reversed")
# open -> partially_paid -> paid; void only while nothing is paid.
BILL_STATUSES = ("open", "partially_paid", "paid", "void")
MATCH_STATUSES = ("matched", "mismatch", "no_po")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class VendorReturn(Base):
    """FR-PUR-008: stock sent back to a vendor; the vendor owes `credit_amount` until a
    credit note is recorded and applied to a bill."""

    __tablename__ = "vendor_returns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("vendor_id", "vendors"),
        _fk("receipt_id", "goods_receipts"),
        _fk("applied_bill_id", "vendor_bills"),
        _check_in("reason", RETURN_REASONS),
        _check_in("status", RETURN_STATUSES),
        CheckConstraint("credit_amount >= 0", name="credit_amount"),
        CheckConstraint("stock_value >= 0", name="stock_value"),
        Index(None, "tenant_id", "vendor_id", "status"),
        Index(None, "tenant_id", "outlet_id", "business_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    vendor_id: Mapped[uuid.UUID] = mapped_column()
    receipt_id: Mapped[uuid.UUID | None] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    stock_value: Mapped[int] = mapped_column(BigInteger)  # stock out, at average cost
    credit_amount: Mapped[int] = mapped_column(BigInteger)  # what the vendor owes back
    credit_note_number: Mapped[str | None] = mapped_column(String(80))
    credited_on: Mapped[date | None] = mapped_column(Date)
    applied_bill_id: Mapped[uuid.UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class VendorReturnLine(Base):
    __tablename__ = "vendor_return_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "return_id"], ["vendor_returns.tenant_id", "vendor_returns.id"]
        ),
        _fk("item_id", "items"),
        _fk("batch_id", "stock_batches"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("credit_amount >= 0", name="credit_amount"),
        Index(None, "tenant_id", "return_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    return_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit
    batch_id: Mapped[uuid.UUID | None] = mapped_column()  # None: earliest expiry first
    credit_amount: Mapped[int] = mapped_column(BigInteger)


class VendorBill(Base):
    """FR-PUR-009: the vendor's invoice, due on `due_date`, checked against PO and receipts."""

    __tablename__ = "vendor_bills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "vendor_id", "vendor_invoice_no"),
        _fk("outlet_id", "outlets"),
        _fk("vendor_id", "vendors"),
        _fk("po_id", "purchase_orders"),
        _check_in("status", BILL_STATUSES),
        _check_in("match_status", MATCH_STATUSES),
        CheckConstraint("total >= 0", name="total"),
        CheckConstraint("paid >= 0 AND credited >= 0", name="settled"),
        CheckConstraint("paid + credited <= total", name="not_overpaid"),
        Index(None, "tenant_id", "status", "due_date"),
        Index(None, "tenant_id", "vendor_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    vendor_id: Mapped[uuid.UUID] = mapped_column()
    vendor_invoice_no: Mapped[str] = mapped_column(String(80))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    po_id: Mapped[uuid.UUID | None] = mapped_column()
    bill_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total: Mapped[int] = mapped_column(BigInteger)
    paid: Mapped[int] = mapped_column(BigInteger, server_default="0")
    credited: Mapped[int] = mapped_column(BigInteger, server_default="0")  # vendor credits
    status: Mapped[str] = mapped_column(Text, server_default="open")
    match_status: Mapped[str] = mapped_column(Text)
    match_notes: Mapped[list[dict[str, object]]] = mapped_column(JSONB, server_default="[]")
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class VendorBillLine(Base):
    __tablename__ = "vendor_bill_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "bill_id"], ["vendor_bills.tenant_id", "vendor_bills.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("amount >= 0", name="amount"),
        Index(None, "tenant_id", "bill_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    bill_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit
    amount: Mapped[int] = mapped_column(BigInteger)


class VendorBillReceipt(Base):
    """Which goods receipts a bill covers (on at most one bill that is not void)."""

    __tablename__ = "vendor_bill_receipts"
    __table_args__ = (
        Index(None, "tenant_id", "receipt_id"),
        ForeignKeyConstraint(
            ["tenant_id", "bill_id"], ["vendor_bills.tenant_id", "vendor_bills.id"]
        ),
        _fk("receipt_id", "goods_receipts"),
        Index(None, "tenant_id", "bill_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    bill_id: Mapped[uuid.UUID] = mapped_column()
    receipt_id: Mapped[uuid.UUID] = mapped_column()


class VendorPayment(Base):
    """FR-PUR-009: money paid against a bill. Append-only: a mistake is a negative payment
    that names the one it reverses."""

    __tablename__ = "vendor_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "reverses_id"),
        ForeignKeyConstraint(
            ["tenant_id", "bill_id"], ["vendor_bills.tenant_id", "vendor_bills.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reverses_id"], ["vendor_payments.tenant_id", "vendor_payments.id"]
        ),
        CheckConstraint("amount <> 0", name="amount"),
        Index(None, "tenant_id", "bill_id"),
        Index(None, "tenant_id", "paid_on"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    bill_id: Mapped[uuid.UUID] = mapped_column()
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(40))  # a payment method code (tenant setting)
    reference: Mapped[str | None] = mapped_column(String(120))
    reverses_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
