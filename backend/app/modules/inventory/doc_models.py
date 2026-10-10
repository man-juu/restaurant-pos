"""Stock documents that post to the ledger (docs/05 section 2.3, FR-INV-007 to 009):
waste logs, adjustments and stock counts. Each keeps its own lines; the stock effect is
in `stock_movements` (doc_type = table name, doc_id = header id)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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

WASTE_REASONS = ("spoilage", "expired", "preparation_loss", "damaged", "staff_meal", "other")
ADJUSTMENT_REASONS = ("correction", "found", "theft", "damaged", "other")
COUNT_TYPES = ("full", "spot", "cycle")
# draft: being written; submitted: waiting for approval; posted: in the ledger.
FLOW_STATUSES = ("draft", "submitted", "posted", "rejected")
WASTE_STATUSES = ("posted", "reversed")


def _outlet_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"])


def _item_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"])


def _header_fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"], ondelete="CASCADE"
    )


class _Header:
    """Columns every stock document header has."""

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    number: Mapped[str] = mapped_column(String(40))
    business_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class _Flow(_Header):
    """Documents that may need approval (FR-TEN-007)."""

    status: Mapped[str] = mapped_column(Text, server_default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column()


class WasteLog(_Header, Base):
    __tablename__ = "waste_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        _outlet_fk(),
        _check_in("reason_code", WASTE_REASONS),
        _check_in("status", WASTE_STATUSES),
        Index(None, "tenant_id", "outlet_id", "business_date"),
    )

    reason_code: Mapped[str] = mapped_column(Text)
    photo_ref: Mapped[str | None] = mapped_column(String(200))  # optional, with uploads (1b-3)
    status: Mapped[str] = mapped_column(Text, server_default="posted")


class WasteLine(Base):
    __tablename__ = "waste_lines"
    __table_args__ = (
        _header_fk("waste_id", "waste_logs"),
        _item_fk(),
        CheckConstraint("qty > 0", name="qty_positive"),
        Index(None, "tenant_id", "waste_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    waste_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # as entered, in unit_id
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))


class Adjustment(_Flow, Base):
    __tablename__ = "adjustments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        _outlet_fk(),
        _check_in("reason_code", ADJUSTMENT_REASONS),
        _check_in("status", FLOW_STATUSES),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    reason_code: Mapped[str] = mapped_column(Text)


class AdjustmentLine(Base):
    __tablename__ = "adjustment_lines"
    __table_args__ = (
        _header_fk("adjustment_id", "adjustments"),
        _item_fk(),
        CheckConstraint("qty <> 0", name="qty_not_zero"),
        Index(None, "tenant_id", "adjustment_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    adjustment_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # signed, as entered in unit_id
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    expiry_date: Mapped[date | None] = mapped_column(Date)  # for stock that is added


class StockCount(_Flow, Base):
    """FR-INV-007. System quantities are frozen when the count starts; posting books the
    difference between counted and frozen quantities as count corrections."""

    __tablename__ = "stock_counts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        _outlet_fk(),
        _check_in("count_type", COUNT_TYPES),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"], ["storage_locations.tenant_id", "storage_locations.id"]
        ),
        _check_in("status", FLOW_STATUSES),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    count_type: Mapped[str] = mapped_column(Text)
    blind: Mapped[bool] = mapped_column(server_default="false")
    location_id: Mapped[uuid.UUID | None] = mapped_column()  # FR-INV-017: one storage location


class StockCountLine(Base):
    __tablename__ = "stock_count_lines"
    __table_args__ = (
        _header_fk("count_id", "stock_counts"),
        _item_fk(),
        UniqueConstraint("tenant_id", "count_id", "item_id"),
        CheckConstraint("counted_qty IS NULL OR counted_qty >= 0", name="counted_not_negative"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    count_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()  # item-level counts for now
    system_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit, frozen
    counted_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # base unit
