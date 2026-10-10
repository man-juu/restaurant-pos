"""General ledger schemas (FR-FIN-002 to 005, 009)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Money = Annotated[int, Field(ge=0, le=10**15)]
Memo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
AccountType = Literal["asset", "liability", "equity", "revenue", "expense"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountIn(In):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    type: AccountType
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class AccountOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    type: str
    parent_id: uuid.UUID | None
    system_key: str | None
    is_active: bool


class LineIn(In):
    account_id: uuid.UUID
    debit: Money = 0
    credit: Money = 0
    outlet_id: uuid.UUID | None = None
    memo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class OpeningLine(In):
    account_code: str = Field(min_length=1, max_length=20)  # the chart is made by the setup
    debit: Money = 0
    credit: Money = 0


class SetupIn(In):
    """FR-FIN-009: the books start on `start_date`; opening balances as of that day. The
    difference between debits and credits goes to "opening balance equity"."""

    start_date: date
    template: Literal["id_fnb"] = "id_fnb"
    opening: list[OpeningLine] = Field(default_factory=list, max_length=200)


class SetupOut(BaseModel):
    start_date: date
    template: str
    opening_entry_id: uuid.UUID | None


class JournalIn(In):
    entry_date: date
    memo: Memo | None = None
    outlet_id: uuid.UUID | None = None
    attachment_id: uuid.UUID | None = None
    lines: list[LineIn] = Field(min_length=2, max_length=100)


class JournalLineOut(BaseModel):
    account_id: uuid.UUID
    outlet_id: uuid.UUID | None
    debit: int
    credit: int
    memo: str | None


class JournalOut(BaseModel):
    id: uuid.UUID
    number: str
    entry_date: date
    memo: str | None
    outlet_id: uuid.UUID | None
    source_doc_type: str
    status: str
    total: int
    reverses_id: uuid.UUID | None
    attachment_id: uuid.UUID | None
    lines: list[JournalLineOut]


class ReverseIn(In):
    entry_date: date
    memo: Memo | None = None


class PeriodOut(BaseModel):
    year: int
    month: int
    status: str


class TrialRow(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    debit: int
    credit: int
    balance: int  # debit - credit for assets and expenses, credit - debit otherwise


class BalanceSheet(BaseModel):
    as_of: date
    assets: list[TrialRow]
    liabilities: list[TrialRow]
    equity: list[TrialRow]
    current_earnings: int  # revenue - expenses not yet closed into retained earnings
    total_assets: int
    total_liabilities_equity: int


class CashFlow(BaseModel):
    """Direct method from the cash and bank accounts: money in and out by the kind of
    account on the other side of each entry."""

    since: date
    until: date
    opening: int
    operating: int
    investing: int
    financing: int
    closing: int
