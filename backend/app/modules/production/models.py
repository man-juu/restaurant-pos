"""Production tables (docs/05 section 2.5, FR-PRD-001 to 004). Quantities are in the item's
base unit; values are integer minor units; the output unit cost is numeric(18,6)."""

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

# planned -> completed (stock posted) -> reversed; planned -> cancelled.
STATUSES = ("planned", "completed", "cancelled", "reversed")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("item_id", "items"),
        _check_in("status", STATUSES),
        CheckConstraint("planned_qty > 0", name="planned_qty"),
        CheckConstraint("actual_qty IS NULL OR actual_qty > 0", name="actual_qty"),
        CheckConstraint("input_value >= 0", name="input_value"),
        Index(None, "tenant_id", "outlet_id", "production_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()  # the semi-finished item made
    bom_id: Mapped[uuid.UUID | None] = mapped_column()  # recipe version used, if any
    production_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="planned")
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    input_value: Mapped[int] = mapped_column(BigInteger, server_default="0")
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    lot_code: Mapped[str | None] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    completed_by: Mapped[uuid.UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()


class ProductionLine(Base):
    """One component: what the recipe asked for and what was really used."""

    __tablename__ = "production_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"], ["production_orders.tenant_id", "production_orders.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("planned_qty >= 0", name="planned_qty"),
        CheckConstraint("actual_qty IS NULL OR actual_qty >= 0", name="actual_qty"),
        Index(None, "tenant_id", "order_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    value: Mapped[int] = mapped_column(BigInteger, server_default="0")
