"""Delivery-platform settlements and their reconciliation (FR-FIN-007)."""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Amount = Annotated[int, Field(ge=0, le=10**15)]


class SettlementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: uuid.UUID  # a channel of kind "platform"
    outlet_id: uuid.UUID
    account_id: uuid.UUID  # money account the payout arrived in
    period_from: date
    period_to: date
    paid_on: date
    gross: Amount
    commission: Amount = 0
    fees: Amount = 0
    adjustments: Annotated[int, Field(ge=-(10**15), le=10**15)] = 0
    payout: Amount
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )

    @model_validator(mode="after")
    def _adds_up(self) -> Self:
        if self.period_to < self.period_from:
            raise ValueError("period_to is before period_from")
        if self.payout != self.gross - self.commission - self.fees + self.adjustments:
            raise ValueError("payout must equal gross - commission - fees + adjustments")
        return self


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    channel_id: uuid.UUID
    outlet_id: uuid.UUID
    account_id: uuid.UUID
    period_from: date
    period_to: date
    paid_on: date
    gross: int
    commission: int
    fees: int
    adjustments: int
    payout: int
    reference: str | None
    status: str


class ReconcileOut(BaseModel):
    """Our books against the platform's statements for one channel, outlet and period."""

    orders: int  # posted sales documents on the channel
    booked_gross: int  # what our sales say the platform owes
    settled_gross: int  # what settlements in the period say the platform sold
    difference: int  # booked minus settled: missing payouts, or sales we did not record
    commission: int
    fees: int
    adjustments: int
    payout: int
    commission_pct: str | None  # commission and fees as a share of settled gross
    settlements: int
