"""Delivery-platform settlements (FR-FIN-007): one payout statement from a platform for one
outlet and period. Sales stay gross; commission and fees are an expense; the payout clears
the platform receivable. A mistake is reversed (status "reversed"), never edited."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

SETTLEMENT_STATUSES = ("posted", "reversed")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class PlatformSettlement(Base):
    __tablename__ = "platform_settlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "number"),
        _fk("channel_id", "channels"),
        _fk("outlet_id", "outlets"),
        _fk("account_id", "money_accounts"),
        _check_in("status", SETTLEMENT_STATUSES),
        CheckConstraint("period_to >= period_from", name="period"),
        CheckConstraint("gross >= 0 AND commission >= 0 AND fees >= 0", name="amounts"),
        CheckConstraint("payout = gross - commission - fees + adjustments", name="payout"),
        Index(None, "tenant_id", "channel_id", "outlet_id", "period_from"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    channel_id: Mapped[uuid.UUID] = mapped_column()
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column()  # the bank account the payout went into
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    paid_on: Mapped[date] = mapped_column(Date)
    gross: Mapped[int] = mapped_column(BigInteger)  # sales the platform statement shows
    commission: Mapped[int] = mapped_column(BigInteger)
    fees: Mapped[int] = mapped_column(BigInteger)  # promotions, delivery, service fees
    adjustments: Mapped[int] = mapped_column(BigInteger)  # signed: refunds, corrections
    payout: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    reversed_by: Mapped[uuid.UUID | None] = mapped_column()
    reversed_at: Mapped[datetime | None] = mapped_column()
