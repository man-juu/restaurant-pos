"""Reconciliation (Gate 3): each sub-ledger's own total against the books, today.

A difference is expected while opening balances are missing (stock or debts from before the
books' start), when a journal was entered by hand against a control account, or for house
accounts (they post to receivables without an invoice). The accountant decides; nothing is
corrected automatically."""

import uuid
from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.subledger import subledgers
from app.modules.finance import ledger
from app.modules.finance.gl_models import GlAccount

CREDIT_TYPES = ("liability", "equity", "revenue")


class ReconcileRow(BaseModel):
    name: str  # stock_value, open_invoices, owed_to_vendors
    role: str
    account_code: str | None
    subledger: int
    books: int  # the account's balance, in its normal direction
    difference: int  # subledger - books


async def reconcile(db: AsyncSession, tenant_id: uuid.UUID, on: date) -> list[ReconcileRow]:
    accounts = {
        a.system_key: a
        for a in await db.scalars(select(GlAccount).where(GlAccount.system_key.is_not(None)))
    }
    totals = await ledger.balances(db, on)
    rows = []
    for sub, amount in await subledgers(db, tenant_id):
        account = accounts.get(sub.role)
        debit, credit = totals.get(account.id, (0, 0)) if account else (0, 0)
        books = (credit - debit) if account and account.type in CREDIT_TYPES else debit - credit
        rows.append(
            ReconcileRow(
                name=sub.name,
                role=sub.role,
                account_code=account.code if account else None,
                subledger=amount,
                books=books,
                difference=amount - books,
            )
        )
    return rows
