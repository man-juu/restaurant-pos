"""Offline till (FR-SAL-013): what a till needs to keep selling without a connection, and
the finished order it uploads afterwards."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.settings.schemas import PaymentMethod, ServiceChargeSettings, TaxSettings
from app.modules.sales.pos_schemas import In, Label, Note, PosLineIn, PosPayIn


class OfflinePackOut(BaseModel):
    """Totals are worked out on the till with the same rules as the server (docs/05)."""

    enabled: bool
    channel_code: str
    tax: TaxSettings
    service_charge: ServiceChargeSettings
    cash_rounding_step: int
    tips_enabled: bool
    methods: list[PaymentMethod]


class OfflineOrderIn(In):
    client_id: uuid.UUID  # made by the till; a second upload of the same id changes nothing
    outlet_id: uuid.UUID
    channel_id: uuid.UUID
    taken_at: datetime
    label: Label | None = None
    note: Note | None = None
    lines: list[PosLineIn] = Field(min_length=1, max_length=100)
    payment: PosPayIn | None = None  # None: served, not paid yet


class OfflineSyncOut(BaseModel):
    client_id: uuid.UUID
    order_id: uuid.UUID
    number: str
    status: Literal["open", "paid", "cancelled"]
    # Why it is still open: a line or the payment no longer fits (price, shift, method).
    problem: str | None = None
    skipped_lines: int = 0
