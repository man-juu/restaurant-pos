"""Labour cost entry and prime cost (FR-RPT-008). Outlet scope on every call."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.access.policy import Principal, require
from app.core.reports import PeriodDep, outlet_filter
from app.core.tenancy import tenant_session
from app.modules.finance import permissions as perm
from app.modules.finance import prime
from app.modules.finance.prime import LaborIn, PrimeCostOut

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
Create = Annotated[Principal, Depends(require(perm.EXPENSE_CREATE))]
Report = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]


class LaborOut(BaseModel):
    outlet_id: uuid.UUID
    month: date
    amount: int
    note: str | None


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/labor", response_model=list[LaborOut])
async def list_labor(request: Request, p: Report, period: PeriodDep) -> list[LaborOut]:
    async with _db(request, p) as db:
        rows = await prime.labor_rows(db, period, outlet_filter(p, period))
        return [
            LaborOut(outlet_id=r.outlet_id, month=r.month, amount=r.amount, note=r.note)
            for r in rows
        ]


@router.put("/labor", status_code=204)
async def save_labor(body: LaborIn, request: Request, p: Create) -> None:
    """Saving a month again replaces its amount (idempotent; audited)."""
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        await prime.save_labor(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)


@router.get("/prime-cost", response_model=PrimeCostOut)
async def prime_cost(request: Request, p: Report, period: PeriodDep) -> PrimeCostOut:
    async with _db(request, p) as db:
        return await prime.prime_cost(db, period, outlet_filter(p, period))
