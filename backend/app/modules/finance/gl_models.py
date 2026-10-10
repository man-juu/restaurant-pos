"""General ledger (docs/05 2.8, FR-FIN-002 to 005, 009).

Double entry: every posted journal entry's lines have equal debits and credits (checked in
code and by the nightly invariant I-5). Posted entries are never changed; a correction is a
reversing entry. Amounts are integer minor units, one side per line."""

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

ACCOUNT_TYPES = ("asset", "liability", "equity", "revenue", "expense")
# submitted waits for approval (FR-FIN-004); posted is final; a posted entry is undone by a
# new entry that `reverses_id` it.
ENTRY_STATUSES = ("submitted", "posted", "rejected")
PERIOD_STATUSES = ("open", "closed")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class GlAccount(Base):
    __tablename__ = "gl_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "system_key"),
        _fk("parent_id", "gl_accounts"),
        _check_in("type", ACCOUNT_TYPES),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column()
    # Accounts the automatic journals find by role ("cash", "inventory", "sales", ...).
    system_key: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(server_default="true")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "reverses_id"),  # an entry is reversed at most once
        _fk("outlet_id", "outlets"),
        _fk("reverses_id", "journal_entries"),
        _fk("attachment_id", "uploads"),
        _check_in("status", ENTRY_STATUSES),
        Index(None, "tenant_id", "entry_date"),
        Index(None, "tenant_id", "source_doc_type", "source_doc_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    entry_date: Mapped[date] = mapped_column(Date)
    memo: Mapped[str | None] = mapped_column(Text)
    source_doc_type: Mapped[str] = mapped_column(String(40))  # "manual", "opening", ...
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
    total: Mapped[int] = mapped_column(BigInteger)  # sum of debits (= sum of credits)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column()
    attachment_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    submitted_at: Mapped[datetime | None] = mapped_column()
    decided_by: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column()


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "entry_id"], ["journal_entries.tenant_id", "journal_entries.id"]
        ),
        _fk("account_id", "gl_accounts"),
        _fk("outlet_id", "outlets"),
        CheckConstraint(
            "debit >= 0 AND credit >= 0 AND (debit = 0) <> (credit = 0)", name="one_side"
        ),
        Index(None, "tenant_id", "entry_id"),
        Index(None, "tenant_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    entry_id: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column()
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    debit: Mapped[int] = mapped_column(BigInteger, server_default="0")
    credit: Mapped[int] = mapped_column(BigInteger, server_default="0")
    memo: Mapped[str | None] = mapped_column(String(200))


class AccountingPeriod(Base):
    """FR-FIN-005: a month; once closed, nothing can be posted dated inside it."""

    __tablename__ = "accounting_periods"
    __table_args__ = (
        UniqueConstraint("tenant_id", "year", "month"),
        _check_in("status", PERIOD_STATUSES),
        CheckConstraint("month BETWEEN 1 AND 12", name="month"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    year: Mapped[int] = mapped_column()
    month: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="open")
    closed_by: Mapped[uuid.UUID | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()


class LedgerSetup(Base):
    """FR-FIN-009: when the books start. Documents dated before are never journaled."""

    __tablename__ = "ledger_setups"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    start_date: Mapped[date] = mapped_column(Date)
    template: Mapped[str] = mapped_column(String(40))
    opening_entry_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
