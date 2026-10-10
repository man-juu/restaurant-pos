"""Finance-lite (FR-FIN-001, docs/05 2.8): cash and bank accounts, expense categories,
expenses (reversed, never deleted) and transfers between accounts (petty cash top-ups).
Money is integer minor units."""

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

ACCOUNT_KINDS = ("cash", "bank", "petty_cash")
EXPENSE_STATUSES = ("posted", "reversed")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class MoneyAccount(Base):
    __tablename__ = "money_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
        _fk("outlet_id", "outlets"),
        _check_in("kind", ACCOUNT_KINDS),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(Text)
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    opening_balance: Mapped[int] = mapped_column(BigInteger, server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "id"), UniqueConstraint("tenant_id", "name"))

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(server_default="true")
    # FR-FIN-003: the ledger account its expenses are journaled to (None: other expenses).
    gl_account_id: Mapped[uuid.UUID | None] = mapped_column()


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("account_id", "money_accounts"),
        _fk("category_id", "expense_categories"),
        _fk("upload_id", "uploads"),
        _check_in("status", EXPENSE_STATUSES),
        CheckConstraint("amount > 0", name="amount"),
        Index(None, "tenant_id", "outlet_id", "spent_on"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column()
    category_id: Mapped[uuid.UUID] = mapped_column()
    spent_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    payee: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(String(300))
    upload_id: Mapped[uuid.UUID | None] = mapped_column()  # receipt photo
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    reversed_by: Mapped[uuid.UUID | None] = mapped_column()
    reversed_at: Mapped[datetime | None] = mapped_column()


class MoneyTransfer(Base):
    """Money moved between accounts (bank to petty cash); append-only."""

    __tablename__ = "money_transfers"
    __table_args__ = (
        _fk("from_account_id", "money_accounts"),
        _fk("to_account_id", "money_accounts"),
        CheckConstraint("amount > 0 AND from_account_id <> to_account_id", name="valid"),
        Index(None, "tenant_id", "moved_on"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    from_account_id: Mapped[uuid.UUID] = mapped_column()
    to_account_id: Mapped[uuid.UUID] = mapped_column()
    amount: Mapped[int] = mapped_column(BigInteger)
    moved_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class LaborCost(Base):
    """FR-RPT-008: what staff cost an outlet in a month, typed in by hand (no payroll here).
    One row per outlet and month; saving again replaces the amount (audited)."""

    __tablename__ = "labor_costs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "outlet_id", "month"),
        _fk("outlet_id", "outlets"),
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("extract(day from month) = 1", name="first_of_month"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    month: Mapped[date] = mapped_column(Date)  # first day of the month
    amount: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(200))
    updated_by: Mapped[uuid.UUID] = mapped_column()
    updated_at: Mapped[datetime] = _created_at()
