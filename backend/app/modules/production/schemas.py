import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
UsedQty = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
MAX_LINES = 100


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductionPlanIn(Strict):
    """FR-PRD-001: what to make, how much (base unit), where and when."""

    outlet_id: uuid.UUID
    item_id: uuid.UUID
    planned_qty: Qty
    production_date: date
    note: Note | None = None


class ProductionUsedIn(Strict):
    item_id: uuid.UUID
    qty: UsedQty  # base unit; 0 = not used after all


class ProductionCompleteIn(Strict):
    """FR-PRD-002, 003: what really came out and, if different from the recipe, what was used."""

    actual_qty: Qty
    used: list[ProductionUsedIn] = Field(default_factory=list, max_length=MAX_LINES)
    lot_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    expiry_date: date | None = None  # default: production date + shelf life
    confirm_negative: bool = False


class ProductionLineOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    item_name: str = ""
    unit_code: str = ""
    planned_qty: Decimal
    actual_qty: Decimal | None
    value: int | None  # hidden without catalog.cost.view


class ProductionOut(BaseModel):
    id: uuid.UUID
    number: str
    outlet_id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    unit_code: str
    bom_id: uuid.UUID | None
    production_date: date
    status: str
    planned_qty: Decimal
    actual_qty: Decimal | None
    yield_variance: Decimal | None  # actual - planned (FR-PRD-003)
    input_value: int | None  # hidden without catalog.cost.view
    unit_cost: Decimal | None
    expiry_date: date | None
    lot_code: str | None
    note: str | None
    created_at: datetime
    completed_at: datetime | None
    lines: list[ProductionLineOut]


class PrepRow(BaseModel):
    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str
    par_qty: Decimal
    on_hand: Decimal
    planned: Decimal  # already planned for the day, not made yet
    suggested: Decimal  # par - on hand - planned, never below 0
