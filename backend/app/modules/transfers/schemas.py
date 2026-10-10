import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
ZeroOk = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
MAX_LINES = 200


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(lines: list[Any]) -> list[Any]:
    ids = [ln.item_id for ln in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("each item once")
    return lines


class RequestLine(Strict):
    item_id: uuid.UUID
    qty: Qty  # base unit


class TransferRequestIn(Strict):
    """FR-TRF-001: the receiving outlet asks the source for stock."""

    from_outlet_id: uuid.UUID
    to_outlet_id: uuid.UUID
    needed_by: date | None = None
    note: Note | None = None
    lines: list[RequestLine] = Field(min_length=1, max_length=MAX_LINES)

    _lines = field_validator("lines")(_unique)


class ApproveLine(Strict):
    item_id: uuid.UUID
    qty: ZeroOk  # 0 = not sent


class TransferApproveIn(Strict):
    """The source may change quantities (0 drops a line); missing lines keep the request."""

    lines: list[ApproveLine] = Field(default_factory=list, max_length=MAX_LINES)


class TransferShipIn(Strict):
    business_date: date
    confirm_negative: bool = False


class ReceiveLine(Strict):
    item_id: uuid.UUID
    qty: ZeroOk  # what arrived in good condition
    reason: Literal["short", "damaged"] | None = None  # why less than shipped


class TransferReceiveIn(Strict):
    """FR-TRF-003: lines not listed arrived complete."""

    business_date: date
    lines: list[ReceiveLine] = Field(default_factory=list, max_length=MAX_LINES)


class TransferLineOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    item_name: str = ""
    unit_code: str = ""
    requested_qty: Decimal
    approved_qty: Decimal | None
    shipped_qty: Decimal | None
    received_qty: Decimal | None
    discrepancy_reason: str | None
    value: int | None  # hidden without catalog.cost.view
    charge: int | None = None  # FR-TRF-006, hidden like the value


class TransferOut(BaseModel):
    id: uuid.UUID
    number: str
    from_outlet_id: uuid.UUID
    to_outlet_id: uuid.UUID
    status: str
    needed_by: date | None
    note: str | None
    shipped_value: int | None  # hidden without catalog.cost.view
    adjustment_id: uuid.UUID | None
    created_at: datetime
    shipped_on: date | None
    received_on: date | None
    standing_id: uuid.UUID | None = None  # FR-TRF-005: made by a standing order
    charge_total: int | None = None  # FR-TRF-006, hidden without catalog.cost.view
    lines: list[TransferLineOut]
