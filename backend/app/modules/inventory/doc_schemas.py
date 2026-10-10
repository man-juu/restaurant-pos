import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.modules.inventory.schemas import Qty, Strict

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
SignedQty = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]
MAX_LINES = 500

WasteReason = Literal["spoilage", "expired", "preparation_loss", "damaged", "staff_meal", "other"]
AdjustmentReason = Literal["correction", "found", "theft", "damaged", "other"]


def _unique_items[T: BaseModel](lines: list[T]) -> list[T]:
    if len({getattr(ln, "item_id") for ln in lines}) != len(lines):  # noqa: B009
        raise ValueError("one line per item")
    return lines


class QtyLine(Strict):
    item_id: uuid.UUID
    qty: Qty
    unit_id: uuid.UUID


class WasteIn(Strict):
    outlet_id: uuid.UUID
    business_date: date
    reason_code: WasteReason
    note: Note = None
    lines: list[QtyLine] = Field(min_length=1, max_length=MAX_LINES)
    confirm_negative: bool = False  # FR-INV-006 "warn": the user saw the warning

    _unique = field_validator("lines")(_unique_items)


class AdjustmentLineIn(Strict):
    item_id: uuid.UUID
    qty: SignedQty  # + adds stock, - removes it
    unit_id: uuid.UUID
    expiry_date: date | None = None

    @field_validator("qty")
    @classmethod
    def _not_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("quantity cannot be 0")
        return v


class AdjustmentIn(Strict):
    outlet_id: uuid.UUID
    business_date: date
    reason_code: AdjustmentReason
    note: Note = None
    lines: list[AdjustmentLineIn] = Field(min_length=1, max_length=MAX_LINES)

    _unique = field_validator("lines")(_unique_items)


class CountIn(Strict):
    """Full: every item with stock at the outlet, plus `item_ids`. Spot and cycle: only
    `item_ids`. Blind: counters do not see the system quantity."""

    outlet_id: uuid.UUID
    business_date: date
    count_type: Literal["full", "spot", "cycle"]
    blind: bool = False
    location_id: uuid.UUID | None = None  # FR-INV-017: also every item kept there
    note: Note = None
    item_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_LINES)


class CountedLine(Strict):
    item_id: uuid.UUID
    counted_qty: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]  # base unit


class CountedIn(Strict):
    lines: list[CountedLine] = Field(min_length=1, max_length=MAX_LINES)

    _unique = field_validator("lines")(_unique_items)


class DocLine(BaseModel):
    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str  # base unit of system_qty / counted_qty
    qty: Decimal | None = None  # as entered (waste, adjustment)
    unit_id: uuid.UUID | None = None
    system_qty: Decimal | None = None  # counts; hidden in a blind count until submitted
    counted_qty: Decimal | None = None


class StockDocument(BaseModel):
    id: uuid.UUID
    kind: Literal["waste", "adjustment", "count"]
    number: str
    outlet_id: uuid.UUID
    business_date: date
    status: str
    reason_code: str | None = None
    count_type: str | None = None
    blind: bool = False
    location_id: uuid.UUID | None = None
    note: str | None
    created_by: uuid.UUID | None
    lines: list[DocLine] = Field(default_factory=list)
