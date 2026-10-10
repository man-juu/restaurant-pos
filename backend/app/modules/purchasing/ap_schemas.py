"""Schemas for vendor returns, bills and payments (FR-PUR-008, 009)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.modules.purchasing.schemas import MAX_LINES, Money, Qty, Strict

Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
PayRef = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Reason = Literal["damaged", "expired", "wrong_item", "quality", "other"]


def _one_per_item(lines: list[BaseModel]) -> None:
    if len({ln.item_id for ln in lines}) != len(lines):  # type: ignore[attr-defined]
        raise ValueError("one line per item")


class ReturnLineIn(Strict):
    item_id: uuid.UUID
    qty: Qty  # base unit
    batch_id: uuid.UUID | None = None  # which batch goes back; default earliest expiry
    credit_amount: Money | None = None  # default: the price paid on the receipt, else cost


class VendorReturnIn(Strict):
    outlet_id: uuid.UUID
    vendor_id: uuid.UUID
    receipt_id: uuid.UUID | None = None
    business_date: date
    reason: Reason
    lines: list[ReturnLineIn] = Field(min_length=1, max_length=MAX_LINES)
    note: Note | None = None

    @model_validator(mode="after")
    def _lines(self) -> "VendorReturnIn":
        _one_per_item(list(self.lines))
        return self


class CreditNoteIn(Strict):
    credit_note_number: Ref
    credited_on: date
    credit_amount: Money | None = None  # what the vendor actually credited, if different


class ReturnLineOut(BaseModel):
    item_id: uuid.UUID
    qty: Decimal
    batch_id: uuid.UUID | None
    credit_amount: int


class VendorReturnOut(BaseModel):
    id: uuid.UUID
    number: str
    outlet_id: uuid.UUID
    vendor_id: uuid.UUID
    receipt_id: uuid.UUID | None
    business_date: date
    reason: str
    status: str
    stock_value: int
    credit_amount: int
    credit_note_number: str | None
    credited_on: date | None
    applied_bill_id: uuid.UUID | None
    note: str | None
    lines: list[ReturnLineOut]


class BillLineIn(Strict):
    item_id: uuid.UUID
    qty: Qty  # base unit
    amount: Money


class VendorBillIn(Strict):
    vendor_id: uuid.UUID
    vendor_invoice_no: Ref
    outlet_id: uuid.UUID
    po_id: uuid.UUID | None = None
    receipt_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    bill_date: date
    due_date: date | None = None  # default: bill date + the vendor's payment terms
    lines: list[BillLineIn] = Field(min_length=1, max_length=MAX_LINES)
    note: Note | None = None

    @model_validator(mode="after")
    def _lines(self) -> "VendorBillIn":
        _one_per_item(list(self.lines))
        if self.due_date and self.due_date < self.bill_date:
            raise ValueError("due date before bill date")
        return self


class MatchNote(BaseModel):
    """One three-way match finding for an item (FR-PUR-009)."""

    item_id: uuid.UUID
    issue: Literal["not_received", "qty_over_received", "price_over_po", "not_on_po"]
    billed_qty: Decimal
    received_qty: Decimal
    billed_unit_price: Decimal
    po_unit_price: Decimal | None


class BillLineOut(BaseModel):
    item_id: uuid.UUID
    qty: Decimal
    amount: int


class PaymentOut(BaseModel):
    id: uuid.UUID
    paid_on: date
    amount: int
    method: str
    reference: str | None
    reverses_id: uuid.UUID | None


class VendorBillOut(BaseModel):
    id: uuid.UUID
    number: str
    vendor_id: uuid.UUID
    vendor_invoice_no: str
    outlet_id: uuid.UUID
    po_id: uuid.UUID | None
    bill_date: date
    due_date: date
    total: int
    paid: int
    credited: int
    balance: int
    status: str
    match_status: str
    match_notes: list[MatchNote]
    receipt_ids: list[uuid.UUID]
    note: str | None
    lines: list[BillLineOut]
    payments: list[PaymentOut]


class PaymentIn(Strict):
    paid_on: date
    amount: Annotated[int, Field(gt=0, le=10**15)]
    method: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )


class ApplyCreditIn(Strict):
    return_id: uuid.UUID


class PayableRow(BaseModel):
    """Accounts payable aging: what is still owed per bill."""

    bill_id: uuid.UUID
    number: str
    vendor_id: uuid.UUID
    vendor_invoice_no: str
    due_date: date
    balance: int
    days_overdue: int


class BaseLine(BaseModel):
    """A receipt line in the item's base unit, to start a return or a bill from."""

    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str
    qty: Decimal
    amount: int
