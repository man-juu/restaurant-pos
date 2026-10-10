"""Loyalty (FR-SAL-016): a points ledger per guest (append-only, like stock) and vouchers.
Points become a voucher; a voucher pays with the tenant's "voucher" payment method, its code
given as the payment reference."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

ENTRY_KINDS = ("earn", "redeem", "reverse", "adjust")
VOUCHER_STATUSES = ("active", "used", "void")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class LoyaltyEntry(Base):
    """One change to a guest's points. Never updated or deleted; a refund adds a reversal."""

    __tablename__ = "loyalty_entries"
    __table_args__ = (
        _fk("customer_id", "customers"),
        _check_in("kind", ENTRY_KINDS),
        CheckConstraint("points <> 0", name="points"),
        Index(None, "tenant_id", "customer_id", "created_at"),
        # A receipt earns once and is reversed at most once.
        Index(
            "uq_loyalty_entries_document",
            "tenant_id",
            "document_id",
            "kind",
            unique=True,
            postgresql_where=text("document_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(BigInteger)  # + earned, - spent
    document_id: Mapped[uuid.UUID | None] = mapped_column()  # the sales document
    voucher_id: Mapped[uuid.UUID | None] = mapped_column()
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        _fk("customer_id", "customers"),
        _check_in("status", VOUCHER_STATUSES),
        CheckConstraint("amount > 0", name="amount"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(BigInteger)  # most it pays; any rest is not refunded
    customer_id: Mapped[uuid.UUID | None] = mapped_column()
    points: Mapped[int] = mapped_column(BigInteger, server_default="0")  # 0: issued by hand
    note: Mapped[str | None] = mapped_column(String(200))
    expires_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    used_document_id: Mapped[uuid.UUID | None] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
