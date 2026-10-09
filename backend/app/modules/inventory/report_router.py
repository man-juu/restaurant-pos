"""Stock reports (FR-RPT-004, 006, FR-INV-015). Outlet scope and cost visibility apply."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.access.policy import Principal, require
from app.core.reports import PeriodDep, Report, outlet_filter, respond
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW
from app.modules.inventory import permissions as perm
from app.modules.inventory import reports

router = APIRouter(prefix="/api/v1/inventory/reports", tags=["inventory"])
View = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]
Lang = Literal["en", "id"]
Kind = Literal["movements", "waste", "expiry", "variance"]


@router.get("/{kind}", response_model=Report)
async def stock_report(
    kind: Kind, request: Request, p: View, period: PeriodDep, lang: Lang = "en"
) -> Report | Response:
    outlets = outlet_filter(p, period)
    cost = p.can(COST_VIEW)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        if kind == "expiry":
            report = await reports.expiry(db, p.tenant_id, period, outlets, language=lang)
        else:
            run = {
                "movements": reports.movements,
                "waste": reports.waste,
                "variance": reports.variance,
            }[kind]
            report = await run(db, p.tenant_id, period, outlets, language=lang, show_cost=cost)
    return respond(report, period, f"stock-{kind}")
