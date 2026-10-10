"""POS orders, payments and cash shifts (FR-SAL-004 to 006, 009). Money is integer minor
units; quantities are decimals in the item's base unit."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Qty = Annotated[Decimal, Field(gt=0, le=10_000, max_digits=18, decimal_places=4)]
Money = Annotated[int, Field(ge=0, le=10**12)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PosOrderCreateIn(In):
    outlet_id: uuid.UUID
    channel_id: uuid.UUID
    label: Label | None = None
    note: Note | None = None


class PosLineIn(In):
    item_id: uuid.UUID
    qty: Qty = Decimal(1)
    option_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    note: Note | None = None


class PosLineUpdateIn(In):
    qty: Qty
    note: Note | None = None


class PosPaymentIn(In):
    method: Code
    amount: Annotated[int, Field(gt=0, le=10**12)]  # what this tender pays of the bill
    tendered: Money | None = None  # cash handed over; change = tendered - amount
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = (
        None
    )


class PosPayIn(In):
    payments: list[PosPaymentIn] = Field(min_length=1, max_length=10)
    tip: Money = 0


class PosModifierOut(BaseModel):
    option_id: uuid.UUID
    name: str
    price_delta: int


class PosLineOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    name: str
    qty: Decimal
    unit_price: int  # list price plus modifier changes
    modifiers: list[PosModifierOut]
    line_total: int
    discount: int = 0  # FR-SAL-007, already rounded
    discount_reason: str | None = None
    note: str | None
    status: Literal["new", "sent", "void"]
    void_reason: str | None = None


class PosTotalsOut(BaseModel):
    subtotal: int  # lines at their prices
    discount: int = 0
    service_charge: int
    tax: int
    total: int


class PosPaymentOut(BaseModel):
    method: str
    kind: str
    amount: int
    tendered: int | None
    change: int
    reference: str | None


class PosOrderOut(BaseModel):
    id: uuid.UUID
    number: str
    status: Literal["open", "paid", "cancelled", "void", "refunded"]
    outlet_id: uuid.UUID
    channel_id: uuid.UUID
    label: str | None
    note: str | None
    created_at: datetime
    paid_at: datetime | None
    lines: list[PosLineOut]
    totals: PosTotalsOut
    document_id: uuid.UUID | None = None
    tip: int = 0
    rounding: int = 0
    payments: list[PosPaymentOut] = Field(default_factory=list)
    discount_kind: Literal["percent", "amount"] | None = None
    discount_value: int | None = None
    discount_reason: str | None = None
    refund: "RefundOut | None" = None


class PosOrderSummary(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    label: str | None
    channel_id: uuid.UUID
    created_at: datetime
    total: int
    lines: int


class ShiftOpenIn(In):
    outlet_id: uuid.UUID
    opening_float: Money


class MovementIn(In):
    kind: Literal["in", "out"]
    amount: Annotated[int, Field(gt=0, le=10**12)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ShiftCloseIn(In):
    counted: Money
    note: Note | None = None


class MovementOut(BaseModel):
    kind: str
    amount: int
    reason: str
    created_at: datetime


class ShiftOut(BaseModel):
    id: uuid.UUID
    outlet_id: uuid.UUID
    cashier_id: uuid.UUID
    cashier_name: str
    status: Literal["open", "closed"]
    opening_float: int
    opened_at: datetime
    closed_at: datetime | None
    cash_sales: int  # cash kept from sales (after change)
    cash_in: int
    cash_out: int
    cash_refunds: int = 0  # FR-SAL-008, paid back in cash from this drawer
    expected: int  # opening float + cash sales + in - out - refunds
    counted: int | None
    variance: int | None  # counted - expected, once closed
    by_method: dict[str, int]  # what was paid per method in this shift
    orders: int
    note: str | None
    movements: list[MovementOut]


class ShiftFilter(BaseModel):
    outlet_id: uuid.UUID
    date_from: date
    date_to: date


class DiscountIn(In):
    """FR-SAL-007: percent in basis points (1000 = 10 %) or an amount in minor units."""

    kind: Literal["percent", "amount"]
    value: Annotated[int, Field(gt=0, le=10**12)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class VoidIn(In):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class RefundIn(In):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    stock_effect: Literal["return", "waste"]
    method: Code  # how the money goes back


class RefundOut(BaseModel):
    id: uuid.UUID
    status: Literal["requested", "done", "rejected"]
    reason: str
    stock_effect: str
    amount: int
    method: str
    created_by: uuid.UUID | None
    decided_by: uuid.UUID | None


PosOrderOut.model_rebuild()
