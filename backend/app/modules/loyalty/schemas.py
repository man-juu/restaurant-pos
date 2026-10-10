import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Code = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, min_length=4, max_length=20, pattern=r"^[A-Z0-9-]+$"
    ),
]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EarnIn(In):
    document_id: uuid.UUID
    customer_id: uuid.UUID


class RedeemIn(In):
    customer_id: uuid.UUID
    points: Annotated[int, Field(ge=1, le=10**9)]


class VoucherIn(In):
    amount: Annotated[int, Field(ge=1, le=10**12)]
    customer_id: uuid.UUID | None = None
    expires_on: date | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class EntryOut(BaseModel):
    id: uuid.UUID
    kind: str
    points: int
    document_id: uuid.UUID | None
    voucher_id: uuid.UUID | None
    created_at: datetime


class VoucherOut(BaseModel):
    id: uuid.UUID
    code: str
    amount: int
    customer_id: uuid.UUID | None
    points: int
    note: str | None
    expires_on: date | None
    status: str
    used_document_id: uuid.UUID | None
    created_at: datetime


class EarnOut(BaseModel):
    points: int  # earned by this receipt (0 when it is too small)
    balance: int


class BalanceOut(BaseModel):
    customer_id: uuid.UUID
    balance: int
    point_value: int
    min_redeem_points: int
    entries: list[EntryOut]  # newest first, at most 50
    vouchers: list[VoucherOut]  # active ones
