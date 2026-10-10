"""Trial balance, balance sheet and cash flow summary from posted journals (FR-FIN-002)."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance import ledger
from app.modules.finance.gl_models import GlAccount, JournalEntry, JournalLine
from app.modules.finance.gl_schemas import BalanceSheet, CashFlow, TrialRow

DEBIT_NORMAL = ("asset", "expense")
CASH_KEYS = ("cash", "bank")


def _row(a: GlAccount, debit: int, credit: int) -> TrialRow:
    balance = debit - credit if a.type in DEBIT_NORMAL else credit - debit
    return TrialRow(
        account_id=a.id,
        code=a.code,
        name=a.name,
        type=a.type,
        debit=debit,
        credit=credit,
        balance=balance,
    )


async def trial_balance(db: AsyncSession, until: date, since: date | None = None) -> list[TrialRow]:
    sums = await ledger.balances(db, until, since)
    accounts = list(await db.scalars(select(GlAccount).order_by(GlAccount.code)))
    return [_row(a, *sums[a.id]) for a in accounts if a.id in sums]


async def balance_sheet(db: AsyncSession, as_of: date) -> BalanceSheet:
    rows = await trial_balance(db, as_of)
    by = {t: [r for r in rows if r.type == t] for t in ("asset", "liability", "equity")}
    earnings = sum(r.balance for r in rows if r.type == "revenue") - sum(
        r.balance for r in rows if r.type == "expense"
    )
    assets = sum(r.balance for r in by["asset"])
    other = sum(r.balance for r in by["liability"]) + sum(r.balance for r in by["equity"])
    return BalanceSheet(
        as_of=as_of,
        assets=by["asset"],
        liabilities=by["liability"],
        equity=by["equity"],
        current_earnings=earnings,
        total_assets=assets,
        total_liabilities_equity=other + earnings,
    )


def _bucket(account_type: str, code: str) -> str:
    """Where money on the other side of an entry belongs (simple direct method)."""
    if account_type == "equity" or (account_type == "liability" and code.startswith("2-2")):
        return "financing"  # owner money, long-term loans
    if account_type == "asset" and code.startswith("1-2"):
        return "investing"  # equipment and other fixed assets
    return "operating"


async def cash_flow(db: AsyncSession, since: date, until: date) -> CashFlow:
    cash = {
        a.id for a in await db.scalars(select(GlAccount).where(GlAccount.system_key.in_(CASH_KEYS)))
    }
    # Opening balances posted at the books' start count as where cash began, not as a flow.
    opening = await _cash_balance(db, cash, since - timedelta(days=1)) + await _opening_cash(
        db, cash, since, until
    )
    flows = {"operating": 0, "investing": 0, "financing": 0}
    entries = (
        select(JournalEntry.id)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == "posted",
            JournalEntry.source_doc_type != "opening",
            JournalEntry.entry_date >= since,
            JournalEntry.entry_date <= until,
            JournalLine.account_id.in_(cash),
        )
    )
    other = (
        select(GlAccount.type, GlAccount.code, func.sum(JournalLine.credit - JournalLine.debit))
        .join(JournalLine, JournalLine.account_id == GlAccount.id)
        .where(JournalLine.entry_id.in_(entries), JournalLine.account_id.not_in(cash))
        .group_by(GlAccount.type, GlAccount.code)
    )
    for account_type, code, amount in (await db.execute(other)).all():
        flows[_bucket(account_type, code)] += int(amount)
    return CashFlow(
        since=since, until=until, opening=opening, closing=opening + sum(flows.values()), **flows
    )


async def _cash_balance(db: AsyncSession, cash: set[uuid.UUID], until: date) -> int:
    sums = await ledger.balances(db, until)
    return sum(sums[a][0] - sums[a][1] for a in cash if a in sums)


async def _opening_cash(db: AsyncSession, cash: set[uuid.UUID], since: date, until: date) -> int:
    stmt = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalEntry.status == "posted",
            JournalEntry.source_doc_type == "opening",
            JournalEntry.entry_date >= since,
            JournalEntry.entry_date <= until,
            JournalLine.account_id.in_(cash),
        )
    )
    return int(await db.scalar(stmt) or 0)
