"""Wholesale invoices, receivables and aging (FR-SAL-011, FR-FIN-006)."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.modules.sales.schemas import MAX_LINES, EntryLine, Money, Strict

Ref = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class InvoiceIn(Strict):
    outlet_id: uuid.UUID  # where the goods leave from
    channel_id: uuid.UUID  # a wholesale channel (its price list and tax rules)
    customer_id: uuid.UUID
    invoice_date: date
    due_date: date | None = None  # default: invoice date + the payment terms setting
    lines: list[EntryLine] = Field(min_length=1, max_length=MAX_LINES)
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class InvoiceLineOut(BaseModel):
    item_id: uuid.UUID
    qty: str
    unit_price: int


class InvoiceOut(BaseModel):
    id: uuid.UUID  # the receivable
    document_id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: str
    outlet_id: uuid.UUID
    invoice_date: date
    due_date: date
    subtotal: int
    tax: int
    total: int
    paid: int
    balance: int
    status: str
    lines: list[InvoiceLineOut]


class ReceiptIn(Strict):
    """Money received from the customer against an invoice."""

    paid_on: date
    amount: Annotated[int, Field(gt=0, le=10**15)]
    method: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    reference: Ref | None = None


__all__ = ["InvoiceIn", "InvoiceOut", "Money", "ReceiptIn"]
