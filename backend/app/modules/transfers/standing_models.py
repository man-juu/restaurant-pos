"""Standing transfer orders (FR-TRF-005): "every Monday and Thursday, send us these items".
A periodic task turns each into a normal transfer request `lead_days` before the day."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id
from app.modules.transfers.models import _fk


class StandingTransfer(Base):
    __tablename__ = "standing_transfers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("from_outlet_id", "outlets"),
        _fk("to_outlet_id", "outlets"),
        CheckConstraint("from_outlet_id <> to_outlet_id", name="two_outlets"),
        CheckConstraint("weekdays BETWEEN 1 AND 127", name="weekdays"),  # bit 0 = Monday
        CheckConstraint("lead_days BETWEEN 0 AND 6", name="lead_days"),
        Index(None, "tenant_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    from_outlet_id: Mapped[uuid.UUID] = mapped_column()
    to_outlet_id: Mapped[uuid.UUID] = mapped_column()
    weekdays: Mapped[int] = mapped_column(SmallInteger)
    lead_days: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    is_active: Mapped[bool] = mapped_column(server_default="true")
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class StandingTransferLine(Base):
    __tablename__ = "standing_transfer_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "standing_id", "item_id"),
        _fk("standing_id", "standing_transfers"),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    standing_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit
