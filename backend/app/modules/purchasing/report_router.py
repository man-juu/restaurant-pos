"""Purchase reports (FR-RPT-005, 006). Outlet scope applies; amounts need cost view."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.access.policy import Principal, require
from app.core.errors import ForbiddenError
from app.core.reports import PeriodDep, Report, outlet_filter, respond
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW
from app.modules.purchasing import permissions as perm
from app.modules.purchasing import reports
from app.modules.purchasing.reports import By

router = APIRouter(prefix="/api/v1/purchasing/reports", tags=["purchasing"])
View = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]


@router.get("/purchases", response_model=Report)
async def purchases(
    request: Request,
    p: View,
    period: PeriodDep,
    by: By = "vendor",
    lang: Literal["en", "id"] = "en",
) -> Report | Response:
    outlets = outlet_filter(p, period)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        report = await reports.purchases(
            db, p.tenant_id, period, outlets, by, language=lang, show_cost=p.can(COST_VIEW)
        )
    return respond(report, period, f"purchases-by-{by}")


@router.get("/price-trend", response_model=Report)
async def price_trend(
    item_id: uuid.UUID, request: Request, p: View, period: PeriodDep
) -> Report | Response:
    if not p.can(COST_VIEW):  # nothing but prices here: no cost view, no report
        raise ForbiddenError("permission_denied", details={"permission": COST_VIEW})
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        report = await reports.price_trend(db, period, item_id)
    return respond(report, period, "price-trend")
