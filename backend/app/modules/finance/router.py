"""Finance-lite endpoints (FR-FIN-001). Outlet scope on expenses and reports."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.reports import PeriodDep, outlet_filter
from app.core.tenancy import tenant_session
from app.modules.finance import permissions as perm
from app.modules.finance import service
from app.modules.finance.models import Expense, ExpenseCategory
from app.modules.finance.schemas import (
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseIn,
    ExpenseOut,
    MoneyAccountIn,
    MoneyAccountOut,
    ProfitLossOut,
    TransferIn,
)

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
View = Annotated[Principal, Depends(require(perm.EXPENSE_VIEW))]
Create = Annotated[Principal, Depends(require(perm.EXPENSE_CREATE))]
Manage = Annotated[Principal, Depends(require(perm.ACCOUNT_MANAGE))]
Report = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/accounts", response_model=list[MoneyAccountOut])
async def accounts(request: Request, p: View) -> list[MoneyAccountOut]:
    async with _db(request, p) as db:
        return await service.balances(db)


@router.post("/accounts", response_model=list[MoneyAccountOut], status_code=201)
async def create_account(
    body: MoneyAccountIn, request: Request, p: Manage
) -> list[MoneyAccountOut]:
    async with _db(request, p) as db:
        await service.save_account(db, p.tenant_id, p.user_id, body)
        return await service.balances(db)


@router.put("/accounts/{account_id}", response_model=list[MoneyAccountOut])
async def update_account(
    account_id: uuid.UUID, body: MoneyAccountIn, request: Request, p: Manage
) -> list[MoneyAccountOut]:
    async with _db(request, p) as db:
        await service.save_account(db, p.tenant_id, p.user_id, body, account_id)
        return await service.balances(db)


@router.get("/categories", response_model=list[ExpenseCategoryOut])
async def categories(request: Request, p: View) -> list[ExpenseCategoryOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name))
        return [ExpenseCategoryOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/categories", response_model=ExpenseCategoryOut, status_code=201)
async def create_category(
    body: ExpenseCategoryIn, request: Request, p: Manage
) -> ExpenseCategoryOut:
    async with _db(request, p) as db:
        return ExpenseCategoryOut.model_validate(
            await service.save_category(db, p.tenant_id, p.user_id, body), from_attributes=True
        )


@router.put("/categories/{category_id}", response_model=ExpenseCategoryOut)
async def update_category(
    category_id: uuid.UUID, body: ExpenseCategoryIn, request: Request, p: Manage
) -> ExpenseCategoryOut:
    async with _db(request, p) as db:
        row = await service.save_category(db, p.tenant_id, p.user_id, body, category_id)
        return ExpenseCategoryOut.model_validate(row, from_attributes=True)


@router.get("/expenses", response_model=list[ExpenseOut])
async def expenses(
    outlet_id: uuid.UUID, date_from: date, date_to: date, request: Request, p: View
) -> list[ExpenseOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(Expense)
            .where(
                Expense.outlet_id == outlet_id,
                Expense.spent_on >= date_from,
                Expense.spent_on <= date_to,
            )
            .order_by(Expense.spent_on.desc(), Expense.created_at.desc())
            .limit(500)
        )
        return [ExpenseOut.model_validate(r, from_attributes=True) for r in await db.scalars(stmt)]


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def add_expense(body: ExpenseIn, request: Request, p: Create, key: Key) -> Any:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        row = await service.add_expense(db, p.tenant_id, p.user_id, body)
        out = ExpenseOut.model_validate(row, from_attributes=True)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/expenses/{expense_id}/reverse", response_model=ExpenseOut)
async def reverse_expense(expense_id: uuid.UUID, request: Request, p: Create) -> ExpenseOut:
    async with _db(request, p) as db:
        row = await db.get(Expense, expense_id, with_for_update=True)
        if row is None:
            raise NotFoundError("expense_not_found")
        p.require_outlet(row.outlet_id)
        await service.reverse_expense(db, row, p.user_id)
        return ExpenseOut.model_validate(row, from_attributes=True)


@router.post("/transfers", response_model=list[MoneyAccountOut], status_code=201)
async def transfer(body: TransferIn, request: Request, p: Create) -> list[MoneyAccountOut]:
    async with _db(request, p) as db:
        await service.transfer(db, p.tenant_id, p.user_id, body)
        return await service.balances(db)


@router.get("/profit-loss", response_model=ProfitLossOut)
async def profit_loss(request: Request, p: Report, period: PeriodDep) -> ProfitLossOut:
    """FR-FIN-001: sales, HPP and expenses per outlet and period."""
    async with _db(request, p) as db:
        return await service.profit_loss(db, period, outlet_filter(p, period))
