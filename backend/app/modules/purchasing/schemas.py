import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
Money = Annotated[int, Field(ge=0, le=10**15)]
MAX_LINES = 200


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VendorIn(Strict):
    name: Name
    contact_name: Text | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    email: Text | None = None
    address: Annotated[str, StringConstraints(max_length=1000)] | None = None
    tax_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    payment_terms_days: int = Field(default=0, ge=0, le=365)
    lead_time_days: int = Field(default=1, ge=0, le=365)
    # Plain text in; stored encrypted; never returned except through the audited reveal call.
    bank_details: Annotated[str, StringConstraints(max_length=500)] | None = None
    is_active: bool = True


class VendorOut(BaseModel):
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    tax_id: str | None
    payment_terms_days: int
    lead_time_days: int
    has_bank_details: bool
    is_active: bool


class VendorItemIn(Strict):
    item_id: uuid.UUID
    vendor_sku: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = (
        None
    )
    pack_qty: Qty
    pack_unit_id: uuid.UUID
    price: Money  # per pack
    min_order_qty: Qty | None = None
    valid_from: date


class VendorItemOut(VendorItemIn):
    id: uuid.UUID
    vendor_id: uuid.UUID


class QuickLineIn(Strict):
    item_id: uuid.UUID
    qty: Qty
    unit_id: uuid.UUID
    line_total: Money  # what was paid for this line
    lot_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    expiry_date: date | None = None  # pre-filled from shelf life when missing


class QuickPurchaseIn(Strict):
    """FR-PUR-004: a market or cash purchase, received in one step without a PO."""

    outlet_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    vendor_name: Text | None = None  # for a market stall with no vendor record
    business_date: date
    lines: list[QuickLineIn] = Field(min_length=1, max_length=MAX_LINES)
    invoice_upload_id: uuid.UUID | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

    @model_validator(mode="after")
    def _one_line_per_item(self) -> "QuickPurchaseIn":
        if len({ln.item_id for ln in self.lines}) != len(self.lines):
            raise ValueError("one line per item")
        return self


class ReceiptLineOut(BaseModel):
    item_id: uuid.UUID
    qty: Decimal
    unit_id: uuid.UUID
    line_total: int
    lot_code: str | None
    expiry_date: date | None


class ReceiptOut(BaseModel):
    id: uuid.UUID
    number: str
    outlet_id: uuid.UUID
    vendor_id: uuid.UUID | None
    vendor_name: str | None
    po_id: uuid.UUID | None
    business_date: date
    status: str
    total: int
    invoice_upload_id: uuid.UUID | None
    note: str | None
    lines: list[ReceiptLineOut]
