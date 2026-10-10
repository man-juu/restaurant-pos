"""Transfers between outlets (docs/05 2.5, FR-TRF-001 to 004). Quantities are in the item's
base unit. Picks record which batches left the source (lot, expiry, cost) so the delivery
note can list them and the destination receives the same batches at the same cost."""

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

# requested -> approved -> shipped -> received; requested/approved -> cancelled.
STATUSES = ("requested", "approved", "shipped", "received", "cancelled")
DISCREPANCY_REASONS = ("short", "damaged")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("from_outlet_id", "outlets"),
        _fk("to_outlet_id", "outlets"),
        _check_in("status", STATUSES),
        CheckConstraint("from_outlet_id <> to_outlet_id", name="two_outlets"),
        CheckConstraint("shipped_value >= 0", name="shipped_value"),
        Index(None, "tenant_id", "from_outlet_id", "status"),
        Index(None, "tenant_id", "to_outlet_id", "status"),
        UniqueConstraint("tenant_id", "standing_id", "standing_for"),  # never twice a day
        CheckConstraint("charge_total >= 0", name="charge_total"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    from_outlet_id: Mapped[uuid.UUID] = mapped_column()
    to_outlet_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="requested")
    needed_by: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    shipped_value: Mapped[int] = mapped_column(BigInteger, server_default="0")
    adjustment_id: Mapped[uuid.UUID | None] = mapped_column()  # discrepancy (FR-TRF-003)
    requested_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    approved_by: Mapped[uuid.UUID | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column()
    shipped_by: Mapped[uuid.UUID | None] = mapped_column()
    shipped_at: Mapped[datetime | None] = mapped_column()
    shipped_on: Mapped[date | None] = mapped_column(Date)
    received_by: Mapped[uuid.UUID | None] = mapped_column()
    received_at: Mapped[datetime | None] = mapped_column()
    received_on: Mapped[date | None] = mapped_column(Date)
    standing_id: Mapped[uuid.UUID | None] = mapped_column()  # FR-TRF-005: made by a standing order
    standing_for: Mapped[date | None] = mapped_column(Date)  # the delivery day it is for
    charge_total: Mapped[int] = mapped_column(BigInteger, server_default="0")  # FR-TRF-006


class TransferLine(Base):
    __tablename__ = "transfer_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("transfer_id", "item_id"),
        ForeignKeyConstraint(["tenant_id", "transfer_id"], ["transfers.tenant_id", "transfers.id"]),
        _fk("item_id", "items"),
        CheckConstraint("requested_qty > 0", name="requested_qty"),
        CheckConstraint("approved_qty IS NULL OR approved_qty >= 0", name="approved_qty"),
        CheckConstraint("shipped_qty IS NULL OR shipped_qty >= 0", name="shipped_qty"),
        CheckConstraint("received_qty IS NULL OR received_qty >= 0", name="received_qty"),
        CheckConstraint(
            "discrepancy_reason IS NULL OR discrepancy_reason IN ('short', 'damaged')",
            name="discrepancy_reason_valid",
        ),
        Index(None, "tenant_id", "transfer_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    transfer_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    approved_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    shipped_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    received_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    discrepancy_reason: Mapped[str | None] = mapped_column(Text)
    value: Mapped[int] = mapped_column(BigInteger, server_default="0")  # shipped, at source cost
    charge: Mapped[int] = mapped_column(BigInteger, server_default="0")  # FR-TRF-006 price


class TransferPick(Base):
    """One batch that left the source for a line (FEFO), with its lot, expiry and cost."""

    __tablename__ = "transfer_picks"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "transfer_id"], ["transfers.tenant_id", "transfers.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "line_id"], ["transfer_lines.tenant_id", "transfer_lines.id"]
        ),
        CheckConstraint("qty > 0", name="qty"),
        Index(None, "tenant_id", "transfer_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    transfer_id: Mapped[uuid.UUID] = mapped_column()
    line_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()  # None: shipped beyond on hand
    lot_code: Mapped[str | None] = mapped_column(String(64))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
