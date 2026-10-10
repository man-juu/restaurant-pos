"""Reservations and waitlist (FR-TBL-005 to 008)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.tables.schemas import In

GuestName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class Guest(In):
    """An existing customer, or name and phone (found by phone or created)."""

    customer_id: uuid.UUID | None = None
    name: GuestName | None = None
    phone: Phone | None = None


class ReservationIn(In):
    outlet_id: uuid.UUID
    guest: Guest
    party_size: int = Field(ge=1, le=200)
    starts_at: datetime
    duration_min: int | None = Field(default=None, ge=15, le=600)  # default: dwell setting
    table_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    notes: Notes | None = None


class ReservationOut(BaseModel):
    id: uuid.UUID
    outlet_id: uuid.UUID
    customer_id: uuid.UUID
    guest_name: str
    guest_phone: str | None
    no_shows: int  # earlier no-shows of this guest (FR-TBL-007)
    party_size: int
    starts_at: datetime
    duration_min: int
    status: str
    notes: str | None
    table_ids: list[uuid.UUID]
    session_id: uuid.UUID | None


class StatusIn(In):
    status: Literal["confirmed", "no_show", "cancelled", "completed"]


class SeatReservationIn(In):
    channel_id: uuid.UUID


class Suggestion(BaseModel):
    table_ids: list[uuid.UUID]
    names: list[str]
    capacity: int


class WaitIn(In):
    outlet_id: uuid.UUID
    guest: Guest
    party_size: int = Field(ge=1, le=200)


class WaitOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    guest_name: str
    guest_phone: str | None
    party_size: int
    status: str
    added_at: datetime
    estimated_wait_min: int  # FR-TBL-008


class SeatWaitIn(In):
    table_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    channel_id: uuid.UUID
