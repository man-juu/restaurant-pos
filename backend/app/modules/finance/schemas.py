"""Finance-lite (FR-FIN-001)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Money = Annotated[int, Field(gt=0, le=10**12)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MoneyAccountIn(In):
    name: Name
    kind: Literal["cash", "bank", "petty_cash"]
    outlet_id: uuid.UUID | None = None
    opening_balance: int = Field(default=0, ge=-(10**12), le=10**12)
    is_active: bool = True


class MoneyAccountOut(MoneyAccountIn):
    id: uuid.UUID
    balance: int  # opening + transfers in - transfers out - expenses


class ExpenseCategoryIn(In):
    name: Name
    is_active: bool = True
    gl_account_id: uuid.UUID | None = None  # ledger account for these expenses (books)


class ExpenseCategoryOut(ExpenseCategoryIn):
    id: uuid.UUID


class ExpenseIn(In):
    outlet_id: uuid.UUID
    account_id: uuid.UUID
    category_id: uuid.UUID
    spent_on: date
    amount: Money
    payee: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    note: Text300 | None = None
    upload_id: uuid.UUID | None = None


class ExpenseOut(ExpenseIn):
    id: uuid.UUID
    number: str
    status: Literal["posted", "reversed"]


class TransferIn(In):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Money
    moved_on: date
    note: Text300 | None = None


class ProfitLossOut(BaseModel):
    net_sales: int
    service_charge: int
    revenue: int  # net sales + service charge (tax collected is not revenue)
    cost_of_sales: int  # HPP: stock value the sales took
    gross_profit: int
    expenses: dict[str, int]  # per category
    expenses_total: int
    net_profit: int
    tax_collected: int  # owed to the region, shown for reference
