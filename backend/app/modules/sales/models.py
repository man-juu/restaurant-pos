"""Sales (docs/05 2.6). Phase 1 has manual daily entry only: one document per outlet,
channel and business day. Money is integer minor units; quantities numeric(18,4)."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

DAY_STATUSES = ("open", "locked")
DOC_STATUSES = ("posted", "replaced", "reversed")
SOURCES = ("manual_day", "pos")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class SalesDay(Base):
    __tablename__ = "sales_days"
    __table_args__ = (
        UniqueConstraint("tenant_id", "outlet_id", "business_date"),
        _fk("outlet_id", "outlets"),
        _check_in("status", DAY_STATUSES),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    locked_by: Mapped[uuid.UUID | None] = mapped_column()
    locked_at: Mapped[datetime | None] = mapped_column()


class SalesDocument(Base):
    __tablename__ = "sales_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("channel_id", "channels"),
        _check_in("status", DOC_STATUSES),
        _check_in("source", SOURCES),
        CheckConstraint("discount >= 0 AND service_charge >= 0 AND tax >= 0", name="amounts"),
        # One live manual document per outlet, channel and day.
        Index(
            "uq_sales_documents_live_day",
            "tenant_id",
            "outlet_id",
            "channel_id",
            "business_date",
            unique=True,
            postgresql_where=text("status = 'posted' AND source = 'manual_day'"),
        ),
        Index(None, "tenant_id", "outlet_id", "business_date"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    number: Mapped[str] = mapped_column(String(40))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    channel_id: Mapped[uuid.UUID] = mapped_column()
    business_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, server_default="manual_day")
    status: Mapped[str] = mapped_column(Text, server_default="posted")
    subtotal: Mapped[int] = mapped_column(BigInteger)  # list prices x quantities
    discount: Mapped[int] = mapped_column(BigInteger, server_default="0")  # promos
    service_charge: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tax: Mapped[int] = mapped_column(BigInteger, server_default="0")
    total: Mapped[int] = mapped_column(BigInteger)
    cost: Mapped[int] = mapped_column(BigInteger, server_default="0")  # stock value used
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class SalesLine(Base):
    __tablename__ = "sales_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["sales_documents.tenant_id", "sales_documents.id"]
        ),
        _fk("item_id", "items"),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("unit_price >= 0", name="unit_price"),
        Index(None, "tenant_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # base unit of the item
    unit_price: Mapped[int] = mapped_column(BigInteger)  # list price used
    platform_code: Mapped[str | None] = mapped_column(String(64))
    bom_id: Mapped[uuid.UUID | None] = mapped_column()  # recipe version used (docs/05)
