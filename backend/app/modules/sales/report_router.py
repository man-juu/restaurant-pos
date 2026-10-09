"""Sales reports (FR-RPT-001 to 003, 006, 011). Outlet scope and cost visibility apply."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.access.policy import Principal, require
from app.core.reports import PeriodDep, Report, outlet_filter, respond
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW
from app.modules.sales import permissions as perm
from app.modules.sales import reports
from app.modules.sales.reports import Dimension, Grain

router = APIRouter(prefix="/api/v1/sales/reports", tags=["sales"])
View = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]


@router.get("/summary", response_model=Report)
async def summary(
    request: Request, p: View, period: PeriodDep, grain: Grain = "day"
) -> Report | Response:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        report = await reports.summary(
            db, period, outlet_filter(p, period), grain, p.can(COST_VIEW)
        )
    return respond(report, period, f"sales-summary-{grain}")


@router.get("/breakdown", response_model=Report)
async def breakdown(
    request: Request,
    p: View,
    period: PeriodDep,
    by: Dimension = "item",
    lang: Literal["en", "id"] = "en",
) -> Report | Response:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        report = await reports.breakdown(
            db,
            p.tenant_id,
            period,
            outlet_filter(p, period),
            by,
            language=lang,
            show_cost=p.can(COST_VIEW),
        )
    return respond(report, period, f"sales-by-{by}")
