import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
MAX_LINES = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpeningLine(Strict):
    """Stock counted when starting with the system. Quantity and cost per `unit_id`."""

    item_id: uuid.UUID
    qty: Qty
    unit_id: uuid.UUID
    unit_cost: UnitCost  # minor units per unit_id, e.g. 15000 for Rp 15.000 per kg
    lot_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    expiry_date: date | None = None


class OpeningIn(Strict):
    outlet_id: uuid.UUID
    business_date: date
    lines: list[OpeningLine] = Field(min_length=1, max_length=MAX_LINES)

    @field_validator("lines")
    @classmethod
    def _one_line_per_item(cls, v: list[OpeningLine]) -> list[OpeningLine]:
        if len({ln.item_id for ln in v}) != len(v):
            raise ValueError("one line per item")
        return v


class PostedDocument(BaseModel):
    doc_type: str
    doc_id: uuid.UUID
    movements: int


class Labelled(BaseModel):
    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str  # base unit of qty
    tracking_mode: str = "exact"  # "estimated" rows get the "set on hand" correction


class StockRow(Labelled):
    qty: Decimal  # base unit; negative means more was used than was recorded in
    avg_cost: Decimal | None  # hidden without catalog.cost.view
    value: int | None


class BatchOut(BaseModel):
    id: uuid.UUID
    lot_code: str | None
    expiry_date: date | None
    received_at: datetime
    qty: Decimal


class MovementOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    batch_id: uuid.UUID | None
    movement_type: str
    qty: Decimal
    unit_cost: Decimal | None
    value: int | None
    doc_type: str
    doc_id: uuid.UUID
    business_date: date
    posted_at: datetime
    reverses_id: uuid.UUID | None


class ValuationRow(Labelled):
    qty: Decimal
    value: int
