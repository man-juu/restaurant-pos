import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
Money = Annotated[int, Field(ge=0, le=10**15)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
MAX_LINES = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryLine(Strict):
    """An item by id, or by the platform's code (FR-CAT-010)."""

    item_id: uuid.UUID | None = None
    platform_code: Code | None = None
    qty: Qty
    unit_price: Money | None = None  # default: the channel list price on that day

    @model_validator(mode="after")
    def _one_key(self) -> "EntryLine":
        if (self.item_id is None) == (self.platform_code is None):
            raise ValueError("give item_id or platform_code")
        return self


class DayEntryIn(Strict):
    """FR-SAL-002: what one channel sold at one outlet on one day. Saving again replaces
    the earlier entry (its stock comes back first)."""

    outlet_id: uuid.UUID
    business_date: date
    channel_id: uuid.UUID
    lines: list[EntryLine] = Field(min_length=1, max_length=MAX_LINES)
    reported_total: Money | None = None  # what the platform or till says (promos = discount)
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class SalesLineOut(BaseModel):
    item_id: uuid.UUID
    name: str = ""
    qty: Decimal
    unit_price: int
    platform_code: str | None


class SalesDocOut(BaseModel):
    id: uuid.UUID
    number: str
    outlet_id: uuid.UUID
    channel_id: uuid.UUID
    business_date: date
    status: str
    subtotal: int
    discount: int
    service_charge: int
    tax: int
    total: int
    cost: int | None  # hidden without catalog.cost.view
    created_at: datetime
    lines: list[SalesLineOut]


class DayOut(BaseModel):
    outlet_id: uuid.UUID
    business_date: date
    status: str
    documents: list[SalesDocOut]
