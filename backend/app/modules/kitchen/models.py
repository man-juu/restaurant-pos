"""Kitchen stations and tickets (FR-KDS-001 to 004). A ticket is what one station makes for
one order send; its items are copied from the order lines when they are sent, so the
display never reads sales tables."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

TICKET_STATUSES = ("new", "preparing", "ready", "bumped")
ITEM_STATUSES = ("active", "void")


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class KitchenStation(Base):
    """FR-KDS-002: a station (grill, drinks) gets the items of its menu categories; the
    default station gets everything no other station claims."""

    __tablename__ = "kitchen_stations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "outlet_id", "name"),
        _fk("outlet_id", "outlets"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(60))
    category_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid()), server_default="{}")
    is_default: Mapped[bool] = mapped_column(server_default="false")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        _fk("outlet_id", "outlets"),
        _fk("station_id", "kitchen_stations"),
        _fk("order_id", "pos_orders"),
        _check_in("status", TICKET_STATUSES),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    station_id: Mapped[uuid.UUID | None] = mapped_column()  # None: no stations set up yet
    order_id: Mapped[uuid.UUID] = mapped_column()
    order_number: Mapped[str] = mapped_column(String(40))
    label: Mapped[str | None] = mapped_column(String(60))  # table or customer
    channel_name: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str | None] = mapped_column(String(40))  # FR-KDS-003: delivery app
    status: Mapped[str] = mapped_column(Text, server_default="new")
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column()
    ready_at: Mapped[datetime | None] = mapped_column()
    bumped_at: Mapped[datetime | None] = mapped_column()


class KitchenTicketItem(Base):
    __tablename__ = "kitchen_ticket_items"
    __table_args__ = (
        _fk("ticket_id", "kitchen_tickets"),
        _fk("line_id", "pos_order_lines"),
        _check_in("status", ITEM_STATUSES),
        Index(None, "tenant_id", "ticket_id"),
        Index(None, "tenant_id", "line_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    ticket_id: Mapped[uuid.UUID] = mapped_column()
    line_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(200))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    modifiers: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(Text, server_default="active")
