"""Purchasing tables (docs/05 section 2.4, FR-PUR-001 to 006, 011). Part 1: vendors, vendor
items, goods receipts (quick purchase now; receipts against POs in part 2) and price history.
Money is integer minor units; unit costs per base unit are numeric(18,6)."""

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
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

RECEIPT_STATUSES = ("posted", "reversed")
# draft -> submitted (waits for approval) -> approved -> partially_received -> received;
# rejected and cancelled end it. No approval rule: submitting approves at once.
PO_STATUSES = (
    "draft",
    "submitted",
    "approved",
    "rejected",
    "partially_received",
    "received",
    "cancelled",
)


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint("payment_terms_days >= 0", name="terms"),
        CheckConstraint("lead_time_days >= 0", name="lead_time"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(String(40))
    payment_terms_days: Mapped[int] = mapped_column(server_default="0")
    lead_time_days: Mapped[int] = mapped_column(server_default="1")
    # Bank details are encrypted (AES-GCM, app.core.crypto): a database leak does not expose them.
    bank_details_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = _created_at()


class VendorItem(Base):
    """FR-PUR-002: what a vendor sells, in which pack, at which price, from when."""

    __tablename__ = "vendor_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "vendor_id", "item_id", "pack_unit_id", "valid_from"),
        _fk("vendor_id", "vendors"),
        _fk("item_id", "items"),
        CheckConstraint("pack_qty > 0", name="pack_qty"),
        CheckConstraint("price >= 0", name="price"),
        Index(None, "tenant_id", "item_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    vendor_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    vendor_sku: Mapped[str | None] = mapped_column(String(64))
    pack_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # in pack_unit
    pack_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    price: Mapped[int] = mapped_column(BigInteger)  # per pack, minor units
    min_order_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # packs
    valid_from: Mapped[date] = mapped_column(Date)


class PurchaseOrder(Base):
    """FR-PUR-003: an order to one vendor for one outlet, approved by amount (FR-TEN-007)."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("vendor_id", "vendors"),
        _check_in("status", PO_STATUSES),
        CheckConstraint("total >= 0", name="total"),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str | None] = mapped_column(String(40))  # given on submit
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    vendor_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[int] = mapped_column(BigInteger, server_default="0")
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    submitted_at: Mapped[datetime | None] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column()


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "po_id"], ["purchase_orders.tenant_id", "purchase_orders.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("received_qty >= 0", name="received_qty"),
        CheckConstraint("unit_price >= 0", name="unit_price"),
        Index(None, "tenant_id", "po_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    po_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # in unit_id
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    unit_price: Mapped[int] = mapped_column(BigInteger)  # per unit_id, minor units
    received_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), server_default="0")


class VendorLeadHistory(Base):
    """FR-PUR-006: how long a vendor really took, per item (ordered -> received). Append-only."""

    __tablename__ = "vendor_lead_history"
    __table_args__ = (
        _fk("vendor_id", "vendors"),
        _fk("item_id", "items"),
        Index(None, "tenant_id", "vendor_id", "item_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    vendor_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    ordered_at: Mapped[date] = mapped_column(Date)
    received_at: Mapped[date] = mapped_column(Date)
    source_doc_id: Mapped[uuid.UUID] = mapped_column()


class GoodsReceipt(Base):
    """FR-PUR-004/005: stock arriving. `po_id` is NULL for a quick purchase."""

    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("vendor_id", "vendors"),
        _fk("invoice_upload_id", "uploads"),
        _fk("po_id", "purchase_orders"),
        _check_in("status", RECEIPT_STATUSES),
        CheckConstraint("total >= 0", name="total"),
        Index(None, "tenant_id", "outlet_id", "business_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    vendor_id: Mapped[uuid.UUID | None] = mapped_column()
    vendor_name: Mapped[str | None] = mapped_column(String(200))  # market stall, no record
    po_id: Mapped[uuid.UUID | None] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    total: Mapped[int] = mapped_column(BigInteger)
    invoice_upload_id: Mapped[uuid.UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "receipt_id"], ["goods_receipts.tenant_id", "goods_receipts.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("line_total >= 0", name="line_total"),
        Index(None, "tenant_id", "receipt_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    receipt_id: Mapped[uuid.UUID] = mapped_column()
    po_line_id: Mapped[uuid.UUID | None] = mapped_column()  # NULL for a quick purchase
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # in unit_id
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    line_total: Mapped[int] = mapped_column(BigInteger)  # what was paid for the line
    lot_code: Mapped[str | None] = mapped_column(String(64))
    expiry_date: Mapped[date | None] = mapped_column(Date)


class VendorPriceHistory(Base):
    """FR-PUR-006: append-only record of real prices paid, per base unit."""

    __tablename__ = "vendor_price_history"
    __table_args__ = (
        _fk("item_id", "items"),
        Index(None, "tenant_id", "item_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    vendor_id: Mapped[uuid.UUID | None] = mapped_column()  # NULL: market purchase
    item_id: Mapped[uuid.UUID] = mapped_column()
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))  # per base unit
    observed_at: Mapped[date] = mapped_column(Date)
    source_doc_id: Mapped[uuid.UUID] = mapped_column()
