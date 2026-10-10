"""Standing transfer orders (FR-TRF-005) and internal transfer charges (FR-TRF-006)."""

import uuid
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.modules.transfers.schemas import MAX_LINES, Note, RequestLine, Strict, _unique

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class StandingIn(Strict):
    """The receiving outlet's regular order: which weekdays it needs the goods, and how many
    days before each the request is made."""

    from_outlet_id: uuid.UUID
    to_outlet_id: uuid.UUID
    weekdays: list[int] = Field(min_length=1, max_length=7)  # 0 = Monday ... 6 = Sunday
    lead_days: int = Field(default=1, ge=0, le=6)
    is_active: bool = True
    note: Note | None = None
    lines: list[RequestLine] = Field(min_length=1, max_length=MAX_LINES)

    _lines = field_validator("lines")(_unique)

    @field_validator("weekdays")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v) or len(set(v)) != len(v):
            raise ValueError("weekdays are 0 (Monday) to 6 (Sunday), each once")
        return sorted(v)


class StandingLineOut(RequestLine):
    name: str = ""
    unit_code: str = ""


class StandingOut(StandingIn):
    id: uuid.UUID
    lines: list[StandingLineOut]  # type: ignore[assignment]
    next_delivery: date | None  # the next day a request will be made for


class ChargeRow(BaseModel):
    """FR-TRF-006: what one outlet charged another for goods shipped in the period."""

    from_outlet_id: uuid.UUID
    to_outlet_id: uuid.UUID
    transfers: int
    cost: int  # stock value shipped
    charge: int  # what the receiving outlet is charged
