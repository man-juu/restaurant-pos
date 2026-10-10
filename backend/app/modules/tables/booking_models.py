"""Reservations and the walk-in waitlist (docs/05 2.7, FR-TBL-005 to 008)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

# pending -> confirmed -> seated -> completed; pending/confirmed -> no_show or cancelled.
RESERVATION_STATUSES = ("pending", "confirmed", "seated", "completed", "no_show", "cancelled")
HOLDING = ("pending", "confirmed", "seated")  # these keep their tables for their time
WAIT_STATUSES = ("waiting", "seated", "left")
SOURCES = ("staff", "online")  # online: made by the guest on the public booking page


def _fk(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["tenant_id", column], [f"{table}.tenant_id", f"{table}.id"])


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        _fk("outlet_id", "outlets"),
        _fk("customer_id", "customers"),
        _fk("session_id", "table_sessions"),
        _check_in("status", RESERVATION_STATUSES),
        _check_in("source", SOURCES),
        CheckConstraint("party_size > 0", name="party_size"),
        CheckConstraint("duration_min > 0", name="duration"),
        Index(None, "tenant_id", "outlet_id", "starts_at"),
        Index(None, "tenant_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    customer_id: Mapped[uuid.UUID] = mapped_column()
    party_size: Mapped[int] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column()
    duration_min: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    notes: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[uuid.UUID | None] = mapped_column()  # set when the party is seated
    source: Mapped[str] = mapped_column(Text, server_default="staff")
    reminded_at: Mapped[datetime | None] = mapped_column()  # FR-TBL-010: staff sent a reminder
    created_by: Mapped[uuid.UUID | None] = mapped_column()  # None: booked online by the guest
    created_at: Mapped[datetime] = _created_at()


class ReservationTable(Base):
    __tablename__ = "reservation_tables"
    __table_args__ = (
        ForeignKeyConstraint(["reservation_id"], ["reservations.id"]),
        _fk("table_id", "dining_tables"),
        Index(None, "tenant_id", "table_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    table_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        _fk("outlet_id", "outlets"),
        _fk("customer_id", "customers"),
        _fk("session_id", "table_sessions"),
        _check_in("status", WAIT_STATUSES),
        CheckConstraint("party_size > 0", name="party_size"),
        Index(None, "tenant_id", "outlet_id", "status"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    customer_id: Mapped[uuid.UUID] = mapped_column()
    party_size: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(Text, server_default="waiting")
    added_at: Mapped[datetime] = _created_at()
    seated_at: Mapped[datetime | None] = mapped_column()
    session_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()


class BookingLink(Base):
    """FR-TBL-010: a public booking page for one outlet. Only the SHA-256 of the link token is
    stored, so a database leak does not reveal working links; switching a link off is final."""

    __tablename__ = "booking_links"
    __table_args__ = (
        _fk("outlet_id", "outlets"),
        Index(None, "tenant_id", "outlet_id"),
        Index(None, "token_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    token_hint: Mapped[str] = mapped_column(Text)  # last 4 characters, to tell links apart
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    disabled_at: Mapped[datetime | None] = mapped_column()
