"""Floors, tables and table sessions (docs/05 2.7, FR-TBL-001 to 004).

A session is one party at one or more tables (merged tables share a session). Orders are
sales module orders; this module only keeps which orders belong to a session."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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

TABLE_STATUSES = ("available", "occupied", "reserved", "needs_cleaning")
SESSION_STATUSES = ("open", "closed")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "outlet_id", "name"),
        _fk("outlet_id", "outlets"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class DiningTable(Base):
    __tablename__ = "dining_tables"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "outlet_id", "name"),
        _fk("outlet_id", "outlets"),
        _fk("floor_id", "floors"),
        _check_in("status", TABLE_STATUSES),
        CheckConstraint("capacity > 0", name="capacity"),
        Index(None, "tenant_id", "floor_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    floor_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(40))
    capacity: Mapped[int] = mapped_column(server_default="4")
    x: Mapped[int] = mapped_column(server_default="0")  # grid position on the floor
    y: Mapped[int] = mapped_column(server_default="0")
    status: Mapped[str] = mapped_column(Text, server_default="available")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class TableSession(Base):
    __tablename__ = "table_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("channel_id", "channels"),
        _check_in("status", SESSION_STATUSES),
        CheckConstraint("party_size > 0", name="party_size"),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    channel_id: Mapped[uuid.UUID] = mapped_column()  # orders of the session use this channel
    status: Mapped[str] = mapped_column(Text, server_default="open")
    party_size: Mapped[int] = mapped_column(server_default="1")
    opened_by: Mapped[uuid.UUID] = mapped_column()
    opened_at: Mapped[datetime] = _created_at()
    closed_at: Mapped[datetime | None] = mapped_column()
    merged_into: Mapped[uuid.UUID | None] = mapped_column()


class SessionTable(Base):
    """The tables a session sits at; `active` while the party is there."""

    __tablename__ = "table_session_tables"
    __table_args__ = (
        _fk("session_id", "table_sessions"),
        _fk("table_id", "dining_tables"),
        # A table is in at most one open session.
        Index(
            "uq_table_session_tables_active",
            "tenant_id",
            "table_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    table_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    active: Mapped[bool] = mapped_column(server_default="true")


class SessionOrder(Base):
    """POS orders (sales module) that belong to a session."""

    __tablename__ = "table_session_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_id"),
        _fk("session_id", "table_sessions"),
        _fk("order_id", "pos_orders"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
