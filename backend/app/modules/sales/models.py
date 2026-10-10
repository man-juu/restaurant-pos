"""Sales (docs/05 2.6). Posted sales documents come from manual daily entry (one per outlet,
channel and day) or from paid POS orders (one per order). POS orders are the working state
while a table or customer is served; payment posts the document, payments and stock in one
transaction. Money is integer minor units; quantities numeric(18,4)."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

DAY_STATUSES = ("open", "locked")
DOC_STATUSES = ("posted", "replaced", "reversed")
SOURCES = ("manual_day", "pos", "wholesale")
SHIFT_STATUSES = ("open", "closed")
ORDER_STATUSES = ("open", "paid", "cancelled", "void", "refunded")
LINE_STATUSES = ("new", "sent", "void")
DISCOUNT_KINDS = ("percent", "amount")
REFUND_STATUSES = ("requested", "done", "rejected")
STOCK_EFFECTS = ("return", "waste")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class SalesDay(Base):
    __tablename__ = "sales_days"
    __table_args__ = (
        UniqueConstraint("tenant_id", "outlet_id", "business_date"),
        _fk("outlet_id", "outlets"),
        _check_in("status", DAY_STATUSES),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    locked_by: Mapped[uuid.UUID | None] = mapped_column()
    locked_at: Mapped[datetime | None] = mapped_column()


class SalesDocument(Base):
    __tablename__ = "sales_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("channel_id", "channels"),
        _check_in("status", DOC_STATUSES),
        _check_in("source", SOURCES),
        CheckConstraint("discount >= 0 AND service_charge >= 0 AND tax >= 0", name="amounts"),
        # One live manual document per outlet, channel and day.
        Index(
            "uq_sales_documents_live_day",
            "tenant_id",
            "outlet_id",
            "channel_id",
            "business_date",
            unique=True,
            postgresql_where=text("status = 'posted' AND source = 'manual_day'"),
        ),
        Index(None, "tenant_id", "outlet_id", "business_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    channel_id: Mapped[uuid.UUID] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, server_default="manual_day")
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    subtotal: Mapped[int] = mapped_column(BigInteger)  # list prices x quantities
    discount: Mapped[int] = mapped_column(BigInteger, server_default="0")  # promos
    service_charge: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax: Mapped[int] = mapped_column(BigInteger, server_default="0")
    total: Mapped[int] = mapped_column(BigInteger)
    cost: Mapped[int] = mapped_column(BigInteger, server_default="0")  # stock value used
    tip: Mapped[int] = mapped_column(BigInteger, server_default="0")  # FR-SAL-006, not revenue
    rounding: Mapped[int] = mapped_column(
        BigInteger, server_default="0"
    )  # cash rounding (docs/05 6.5)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class SalesLine(Base):
    __tablename__ = "sales_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["sales_documents.tenant_id", "sales_documents.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("unit_price >= 0", name="unit_price"),
        Index(None, "tenant_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit of the item
    unit_price: Mapped[int] = mapped_column(BigInteger)  # list price used
    platform_code: Mapped[str | None] = mapped_column(String(64))
    bom_id: Mapped[uuid.UUID | None] = mapped_column()  # recipe version used (docs/05)


class SalesModifierLine(Base):
    """Modifiers sold with a line, with the name and price as they were (docs/05 2.6)."""

    __tablename__ = "sales_modifier_lines"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "line_id"], ["sales_lines.tenant_id", "sales_lines.id"]),
        _fk("option_id", "modifier_options"),
        Index(None, "tenant_id", "line_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    line_id: Mapped[uuid.UUID] = mapped_column()
    option_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(120))
    price_delta: Mapped[int] = mapped_column(BigInteger)


class CashShift(Base):
    """FR-SAL-009: one cashier's drawer from opening float to closing count."""

    __tablename__ = "cash_shifts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _check_in("status", SHIFT_STATUSES),
        CheckConstraint("opening_float >= 0 AND (counted IS NULL OR counted >= 0)", name="cash"),
        Index(
            "uq_cash_shifts_open",
            "tenant_id",
            "outlet_id",
            "cashier_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index(None, "tenant_id", "outlet_id", "opened_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    cashier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Text, server_default="open")
    opening_float: Mapped[int] = mapped_column(BigInteger)
    opened_at: Mapped[datetime] = _created_at()
    closed_at: Mapped[datetime | None] = mapped_column()
    closed_by: Mapped[uuid.UUID | None] = mapped_column()
    expected: Mapped[int | None] = mapped_column(BigInteger)  # set on close
    counted: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)


class CashMovement(Base):
    """Cash put in or taken out of the drawer during a shift (append-only)."""

    __tablename__ = "cash_movements"
    __table_args__ = (
        _fk("shift_id", "cash_shifts"),
        _check_in("kind", ("in", "out")),
        CheckConstraint("amount > 0", name="amount"),
        Index(None, "tenant_id", "shift_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    shift_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class PosOrder(Base):
    """FR-SAL-005: an order being served; lines can be added until it is paid."""

    __tablename__ = "pos_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("channel_id", "channels"),
        _fk("shift_id", "cash_shifts"),
        _fk("document_id", "sales_documents"),
        _check_in("status", ORDER_STATUSES),
        CheckConstraint(
            "(discount_kind IS NULL) = (discount_value IS NULL)"
            " AND (discount_kind IS NULL OR discount_kind IN ('percent', 'amount'))"
            " AND (discount_value IS NULL OR discount_value > 0)",
            name="discount",
        ),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    channel_id: Mapped[uuid.UUID] = mapped_column()
    number: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(Text, server_default="open")
    label: Mapped[str | None] = mapped_column(String(60))  # customer name or pager number
    note: Mapped[str | None] = mapped_column(Text)
    shift_id: Mapped[uuid.UUID | None] = mapped_column()  # the shift that took the payment
    document_id: Mapped[uuid.UUID | None] = mapped_column()  # posted sale, once paid
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    paid_at: Mapped[datetime | None] = mapped_column()
    paid_by: Mapped[uuid.UUID | None] = mapped_column()
    # FR-SAL-007: one discount on the whole order (percent in basis points, or an amount).
    discount_kind: Mapped[str | None] = mapped_column(Text)
    discount_value: Mapped[int | None] = mapped_column(BigInteger)
    discount_reason: Mapped[str | None] = mapped_column(String(200))
    discount_by: Mapped[uuid.UUID | None] = mapped_column()


class PosOrderLine(Base):
    __tablename__ = "pos_order_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("order_id", "pos_orders"),
        _fk("item_id", "items"),
        _check_in("status", LINE_STATUSES),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint(
            "(discount_kind IS NULL) = (discount_value IS NULL)"
            " AND (discount_kind IS NULL OR discount_kind IN ('percent', 'amount'))"
            " AND (discount_value IS NULL OR discount_value > 0)",
            name="discount",
        ),
        Index(None, "tenant_id", "order_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[int] = mapped_column(BigInteger)  # list price when added
    note: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(Text, server_default="new")
    sent_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    discount_kind: Mapped[str | None] = mapped_column(Text)
    discount_value: Mapped[int | None] = mapped_column(BigInteger)
    discount_reason: Mapped[str | None] = mapped_column(String(200))
    discount_by: Mapped[uuid.UUID | None] = mapped_column()
    void_reason: Mapped[str | None] = mapped_column(String(200))  # FR-SAL-008
    voided_by: Mapped[uuid.UUID | None] = mapped_column()


class PosLineModifier(Base):
    __tablename__ = "pos_line_modifiers"
    __table_args__ = (
        _fk("line_id", "pos_order_lines"),
        _fk("option_id", "modifier_options"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    line_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    option_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price_delta: Mapped[int] = mapped_column(BigInteger)


class Payment(Base):
    """FR-SAL-006: one tender on a paid order (append-only). `amount` is what it pays of the
    bill; for cash, `tendered` is what the customer handed over and `change` went back."""

    __tablename__ = "payments"
    __table_args__ = (
        _fk("order_id", "pos_orders"),
        _fk("document_id", "sales_documents"),
        _fk("shift_id", "cash_shifts"),
        CheckConstraint("amount > 0 AND change >= 0", name="amounts"),
        Index(None, "tenant_id", "document_id"),
        Index(None, "tenant_id", "shift_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    shift_id: Mapped[uuid.UUID | None] = mapped_column()
    method_code: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(Text)  # payment kind from the tenant settings
    amount: Mapped[int] = mapped_column(BigInteger)
    tendered: Mapped[int | None] = mapped_column(BigInteger)
    change: Mapped[int] = mapped_column(BigInteger, server_default="0")
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_at: Mapped[datetime] = _created_at()
    created_by: Mapped[uuid.UUID] = mapped_column()


class SalesRefund(Base):
    """FR-SAL-008: giving the money back for a paid order (docs/05 `voids_refunds`). Needs
    approval by rule (by default a manager, never the person who asked); once done, the
    sale is reversed and the stock comes back or is written off as waste."""

    __tablename__ = "sales_refunds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("order_id", "pos_orders"),
        _fk("document_id", "sales_documents"),
        _fk("shift_id", "cash_shifts"),
        _fk("outlet_id", "outlets"),
        _check_in("status", REFUND_STATUSES),
        _check_in("stock_effect", STOCK_EFFECTS),
        CheckConstraint("amount > 0", name="amount"),
        # One live refund per order: a second request waits for the first to be decided.
        Index(
            "uq_sales_refunds_live",
            "tenant_id",
            "order_id",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
        Index(None, "tenant_id", "shift_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="requested")
    reason: Mapped[str] = mapped_column(String(200))
    stock_effect: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger)  # everything the customer paid
    method_code: Mapped[str] = mapped_column(String(40))
    method_kind: Mapped[str] = mapped_column(Text)
    shift_id: Mapped[uuid.UUID | None] = mapped_column()  # drawer the cash came out of
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    submitted_at: Mapped[datetime | None] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column()
