"""Wholesale invoices and accounts receivable (FR-SAL-011, FR-FIN-006). The invoice itself is
a sales document (source "wholesale", lines and stock as usual); the receivable says who owes
it, by when, and what is paid. Payments are append-only; a mistake is a negative payment."""

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

RECEIVABLE_STATUSES = ("open", "partially_paid", "paid", "void")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class Receivable(Base):
    __tablename__ = "receivables"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id"),
        _fk("document_id", "sales_documents"),
        _fk("customer_id", "customers"),
        _fk("outlet_id", "outlets"),
        _check_in("status", RECEIVABLE_STATUSES),
        CheckConstraint("paid >= 0 AND paid <= total", name="paid"),
        Index(None, "tenant_id", "status", "due_date"),
        Index(None, "tenant_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_id: Mapped[uuid.UUID] = mapped_column()
    customer_id: Mapped[uuid.UUID] = mapped_column()
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total: Mapped[int] = mapped_column(BigInteger)
    paid: Mapped[int] = mapped_column(BigInteger, server_default="0")
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class ReceivablePayment(Base):
    __tablename__ = "receivable_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "reverses_id"),
        _fk("receivable_id", "receivables"),
        _fk("reverses_id", "receivable_payments"),
        CheckConstraint("amount <> 0", name="amount"),
        Index(None, "tenant_id", "receivable_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    receivable_id: Mapped[uuid.UUID] = mapped_column()
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(120))
    reverses_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
