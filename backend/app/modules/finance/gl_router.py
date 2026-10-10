"""General ledger endpoints (FR-FIN-002 to 005, 009). Tenant-wide, like the books."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import tenant_today
from app.modules.finance import books, ledger, statements
from app.modules.finance import permissions as perm
from app.modules.finance.gl_models import GlAccount, JournalEntry, LedgerSetup
from app.modules.finance.gl_schemas import (
    AccountIn,
    AccountOut,
    BalanceSheet,
    CashFlow,
    JournalIn,
    JournalLineOut,
    JournalOut,
    PeriodOut,
    ReverseIn,
    SetupIn,
    SetupOut,
    TrialRow,
)
from app.modules.finance.reconcile import ReconcileRow
from app.modules.finance.reconcile import reconcile as reconcile_books

router = APIRouter(prefix="/api/v1/finance/gl", tags=["finance"])

View = Annotated[Principal, Depends(require(perm.LEDGER_VIEW))]
Setup = Annotated[Principal, Depends(require(perm.LEDGER_SETUP))]
Journal = Annotated[Principal, Depends(require(perm.JOURNAL_CREATE))]
Close = Annotated[Principal, Depends(require(perm.PERIOD_CLOSE))]
Year = Annotated[int, Path(ge=2000, le=2100)]
Month = Annotated[int, Path(ge=1, le=12)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _out(db: AsyncSession, e: JournalEntry) -> JournalOut:
    lines = [
        JournalLineOut.model_validate(ln, from_attributes=True)
        for ln in await ledger.entry_lines(db, e.id)
    ]
    return JournalOut(
        **{k: getattr(e, k) for k in JournalOut.model_fields if k != "lines"}, lines=lines
    )


@router.get("/setup", response_model=SetupOut | None)
async def get_setup(request: Request, p: View) -> SetupOut | None:
    async with _db(request, p) as db:
        row = await db.scalar(select(LedgerSetup))
        return SetupOut.model_validate(row, from_attributes=True) if row else None


@router.post("/setup", response_model=SetupOut, status_code=201)
async def setup(body: SetupIn, request: Request, p: Setup) -> SetupOut:
    async with _db(request, p) as db:
        row = await books.setup(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return SetupOut.model_validate(row, from_attributes=True)


@router.get("/accounts", response_model=list[AccountOut])
async def accounts(request: Request, p: View) -> list[AccountOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(select(GlAccount).order_by(GlAccount.code))
        return [AccountOut.model_validate(a, from_attributes=True) for a in rows]


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def add_account(body: AccountIn, request: Request, p: Setup) -> AccountOut:
    async with _db(request, p) as db:
        await ledger.setup_of(db)
        row = await books.save_account(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return AccountOut.model_validate(row, from_attributes=True)


@router.put("/accounts/{account_id}", response_model=AccountOut)
async def edit_account(
    account_id: uuid.UUID, body: AccountIn, request: Request, p: Setup
) -> AccountOut:
    async with _db(request, p) as db:
        found = await db.get(GlAccount, account_id)
        if found is None:
            raise NotFoundError("account_not_found")
        row = await books.save_account(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, account=found
        )
        return AccountOut.model_validate(row, from_attributes=True)


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_key: str = Field(min_length=1, max_length=40)


@router.put("/accounts/{account_id}/role", response_model=AccountOut)
async def give_role(account_id: uuid.UUID, body: RoleIn, request: Request, p: Setup) -> AccountOut:
    """Which account automatic journals use for a role (the posting rules, FR-FIN-003)."""
    async with _db(request, p) as db:
        found = await db.get(GlAccount, account_id, with_for_update=True)
        if found is None:
            raise NotFoundError("account_not_found")
        row = await books.give_role(
            db, tenant_id=p.tenant_id, user_id=p.user_id, account=found, key=body.system_key
        )
        return AccountOut.model_validate(row, from_attributes=True)


@router.get("/journals", response_model=list[JournalOut])
async def journals(
    since: date,
    until: date,
    request: Request,
    p: View,
    status: Annotated[str | None, Query(pattern="^(submitted|posted|rejected)$")] = None,
) -> list[JournalOut]:
    async with _db(request, p) as db:
        stmt = select(JournalEntry).where(
            JournalEntry.entry_date >= since, JournalEntry.entry_date <= until
        )
        if status:
            stmt = stmt.where(JournalEntry.status == status)
        rows = await db.scalars(
            stmt.order_by(JournalEntry.entry_date, JournalEntry.created_at).limit(500)
        )
        return [await _out(db, e) for e in rows]


@router.post("/journals", response_model=JournalOut, status_code=201)
async def add_journal(body: JournalIn, request: Request, p: Journal) -> JournalOut:
    if body.outlet_id:
        p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        return await _out(db, await books.submit_journal(db, p, body))


@router.post("/journals/{entry_id}/approve", response_model=JournalOut)
async def approve(entry_id: uuid.UUID, request: Request, p: Journal) -> JournalOut:
    async with _db(request, p) as db:
        entry = await books.get_entry(db, entry_id, lock=True)
        await books.decide(db, entry, p, approve=True)
        return await _out(db, entry)


@router.post("/journals/{entry_id}/reject", response_model=JournalOut)
async def reject(entry_id: uuid.UUID, request: Request, p: Journal) -> JournalOut:
    async with _db(request, p) as db:
        entry = await books.get_entry(db, entry_id, lock=True)
        await books.decide(db, entry, p, approve=False)
        return await _out(db, entry)


@router.post("/journals/{entry_id}/reverse", response_model=JournalOut)
async def reverse(entry_id: uuid.UUID, body: ReverseIn, request: Request, p: Journal) -> JournalOut:
    async with _db(request, p) as db:
        entry = await books.get_entry(db, entry_id, lock=True)
        back = await ledger.reverse(
            db, entry, user_id=p.user_id, on=body.entry_date, memo=body.memo
        )
        return await _out(db, back)


@router.get("/periods", response_model=list[PeriodOut])
async def periods(request: Request, p: View) -> list[PeriodOut]:
    async with _db(request, p) as db:
        return [PeriodOut.model_validate(x, from_attributes=True) for x in await books.periods(db)]


@router.post("/periods/{year}/{month}/close", response_model=PeriodOut)
async def close(year: Year, month: Month, request: Request, p: Close) -> PeriodOut:
    async with _db(request, p) as db:
        row = await books.set_period(
            db, tenant_id=p.tenant_id, user_id=p.user_id, year=year, month=month, close=True
        )
        return PeriodOut.model_validate(row, from_attributes=True)


@router.post("/periods/{year}/{month}/reopen", response_model=PeriodOut)
async def reopen(year: Year, month: Month, request: Request, p: Close) -> PeriodOut:
    async with _db(request, p) as db:
        row = await books.set_period(
            db, tenant_id=p.tenant_id, user_id=p.user_id, year=year, month=month, close=False
        )
        return PeriodOut.model_validate(row, from_attributes=True)


@router.get("/trial-balance", response_model=list[TrialRow])
async def trial_balance(
    until: date, request: Request, p: View, since: date | None = None
) -> list[TrialRow]:
    async with _db(request, p) as db:
        return await statements.trial_balance(db, until, since)


@router.get("/reconcile", response_model=list[ReconcileRow])
async def reconcile(request: Request, p: View) -> list[ReconcileRow]:
    """Gate 3: stock, open invoices and vendor debts against their accounts, today."""
    async with _db(request, p) as db:
        today = await tenant_today(db, p.tenant_id)
        return await reconcile_books(db, p.tenant_id, today)


@router.get("/balance-sheet", response_model=BalanceSheet)
async def balance_sheet(as_of: date, request: Request, p: View) -> BalanceSheet:
    async with _db(request, p) as db:
        return await statements.balance_sheet(db, as_of)


@router.get("/cash-flow", response_model=CashFlow)
async def cash_flow(since: date, until: date, request: Request, p: View) -> CashFlow:
    async with _db(request, p) as db:
        return await statements.cash_flow(db, since, until)
