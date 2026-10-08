"""Inventory ledger tables (docs/05 sections 2.3 and 3, FR-INV-001 to 005).

`stock_movements` is the truth and is append-only (grants and a trigger). `stock_balances`
and `item_costs` are caches written in the same transaction as each movement; both can be
rebuilt from the movements. Quantities are numeric(18,4) in the item's base unit, unit costs
numeric(18,6) per base unit, values whole minor units (CLAUDE.md rule 5).
"""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

INBOUND = ("purchase_receipt", "production_output", "transfer_in", "opening_balance")
OUTBOUND = (
    "sale_consumption",
    "production_consumption",
    "transfer_out",
    "waste",
    "vendor_return",
)
EITHER = ("adjustment", "count_correction")  # sign decides the direction
MOVEMENT_TYPES = INBOUND + OUTBOUND + EITHER


def _outlet_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"])


def _item_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"])


class StockBatch(Base):
    """FR-INV-003: one received or produced lot, with its expiry date for FEFO."""

    __tablename__ = "stock_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _outlet_fk(),
        _item_fk(),
        CheckConstraint("unit_cost >= 0", name="unit_cost_not_negative"),
        Index(None, "tenant_id", "outlet_id", "item_id", "expiry_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    lot_code: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = _created_at()
    expiry_date: Mapped[date | None] = mapped_column(Date)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source_doc_type: Mapped[str] = mapped_column(String(40))
    source_doc_id: Mapped[uuid.UUID] = mapped_column()


class StockMovement(Base):
    """Append-only. A correction is a new movement pointing at the one it reverses."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "reverses_id"),  # a movement is reversed at most once
        _outlet_fk(),
        _item_fk(),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"], ["stock_batches.tenant_id", "stock_batches.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reverses_id"], ["stock_movements.tenant_id", "stock_movements.id"]
        ),
        _check_in("movement_type", MOVEMENT_TYPES),
        CheckConstraint("qty <> 0", name="qty_not_zero"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_not_negative"),
        Index(None, "tenant_id", "outlet_id", "item_id", "business_date"),
        Index(None, "tenant_id", "doc_type", "doc_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()  # None: stock taken beyond on hand
    movement_type: Mapped[str] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # signed, base unit
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    value: Mapped[int] = mapped_column(BigInteger)  # signed minor units
    doc_type: Mapped[str] = mapped_column(String(40))
    doc_id: Mapped[uuid.UUID] = mapped_column()
    doc_line_id: Mapped[uuid.UUID | None] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    posted_at: Mapped[datetime] = _created_at()
    posted_by: Mapped[uuid.UUID | None] = mapped_column()
    reverses_id: Mapped[uuid.UUID | None] = mapped_column()


class StockBalance(Base):
    """Cache: qty equals the sum of movements for the same key (invariant I-1)."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "outlet_id", "item_id", "batch_id", postgresql_nulls_not_distinct=True
        ),
        _outlet_fk(),
        _item_fk(),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"], ["stock_batches.tenant_id", "stock_batches.id"]
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))


class ItemCost(Base):
    """FR-INV-005 moving average per item and outlet (invariant I-2: never negative)."""

    __tablename__ = "item_costs"
    __table_args__ = (
        _outlet_fk(),
        _item_fk(),
        CheckConstraint("avg_cost >= 0", name="avg_not_negative"),
        Index(None, "tenant_id", "item_id"),  # tenant-wide unit cost for recipe costing
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    qty_on_hand_for_avg: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StockLevel(Base):
    """Targets per outlet and item (docs/05 2.3): par level for the daily prep list
    (FR-PRD-008), and min / reorder point / max for alerts and reorder hints (slice 1j)."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "outlet_id", "item_id"),
        _outlet_fk(),
        _item_fk(),
        CheckConstraint(
            "coalesce(par_qty, 0) >= 0 AND coalesce(min_qty, 0) >= 0"
            " AND coalesce(reorder_point, 0) >= 0 AND coalesce(max_qty, 0) >= 0"
            " AND coalesce(safety_qty, 0) >= 0",
            name="non_negative",
        ),
        CheckConstraint("lead_time_days IS NULL OR lead_time_days >= 0", name="lead_time"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    par_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    min_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reorder_point: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    max_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    safety_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    lead_time_days: Mapped[int | None] = mapped_column()
