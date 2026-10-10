"""Budgets and actual vs budget (FR-FIN-010). Outlet scope on every call."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.access.policy import Principal, require
from app.core.reports import PeriodDep, outlet_filter
from app.core.tenancy import tenant_session
from app.modules.finance import budget
from app.modules.finance import permissions as perm
from app.modules.finance.budget import BudgetIn, BudgetOut, BudgetReport

router = APIRouter(prefix="/api/v1/finance/budgets", tags=["finance"])
Manage = Annotated[Principal, Depends(require(perm.BUDGET_MANAGE))]
Report = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[BudgetOut])
async def list_budgets(request: Request, p: Report, period: PeriodDep) -> list[BudgetOut]:
    async with _db(request, p) as db:
        saved = await budget.rows(db, period, outlet_filter(p, period))
        return [BudgetOut.model_validate(r, from_attributes=True) for r in saved]


@router.put("", status_code=204)
async def save_budget(body: BudgetIn, request: Request, p: Manage) -> None:
    """Saving a month again replaces it (idempotent; audited)."""
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        await budget.save(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)


@router.get("/vs-actual", response_model=BudgetReport)
async def vs_actual(request: Request, p: Report, period: PeriodDep) -> BudgetReport:
    async with _db(request, p) as db:
        return await budget.report(db, period, outlet_filter(p, period))
