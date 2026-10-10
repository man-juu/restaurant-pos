"""Public booking page and reminders (FR-TBL-010)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.modules.tables.booking_schemas import GuestName, Notes
from app.modules.tables.schemas import In

# A real number to call back on: digits, spaces, +, - and brackets; 8 to 30 characters.
GuestPhone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=8, max_length=30, pattern=r"^[0-9+\-() ]+$"
    ),
]


class OnlineIn(In):
    name: GuestName
    phone: GuestPhone
    party_size: int = Field(ge=1, le=200)
    starts_at: datetime
    notes: Notes | None = None
    consent: Literal[True]  # the guest agrees that the business keeps name and phone


class PageOut(BaseModel):
    business: str
    outlet: str
    timezone: str
    max_party: int
    days_ahead: int


class BookedOut(BaseModel):
    """What the guest sees: no table names, no internal IDs beyond the booking's own."""

    id: uuid.UUID
    starts_at: datetime
    party_size: int
    status: str


class LinkOut(BaseModel):
    id: uuid.UUID
    outlet_id: uuid.UUID
    hint: str
    created_at: datetime
    disabled_at: datetime | None


class NewLinkOut(LinkOut):
    token: str  # shown once; only its hash is stored


class NewLinkIn(In):
    outlet_id: uuid.UUID


class ReminderOut(BaseModel):
    message: str
    phone: str | None
