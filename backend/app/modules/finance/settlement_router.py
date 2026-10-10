"""Delivery-platform settlements and reconciliation (FR-FIN-007). Outlet scope on every call."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.reports import PeriodDep, outlet_filter
from app.core.tenancy import tenant_session
from app.modules.finance import permissions as perm
from app.modules.finance import settlements
from app.modules.finance.settlement_models import PlatformSettlement
from app.modules.finance.settlement_schemas import ReconcileOut, SettlementIn, SettlementOut

router = APIRouter(prefix="/api/v1/finance/settlements", tags=["finance"])
View = Annotated[Principal, Depends(require(perm.REPORT_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.SETTLEMENT_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[SettlementOut])
async def list_settlements(outlet_id: uuid.UUID, request: Request, p: View) -> list[SettlementOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows = await db.scalars(
            select(PlatformSettlement)
            .where(PlatformSettlement.outlet_id == outlet_id)
            .order_by(PlatformSettlement.paid_on.desc())
            .limit(200)
        )
        return [SettlementOut.model_validate(r) for r in rows]


@router.post("", response_model=SettlementOut, status_code=201)
async def create(
    body: SettlementIn, request: Request, p: Manage, key: Key
) -> SettlementOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        row = await settlements.create(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        result = SettlementOut.model_validate(row)
        await remember(db, p.tenant_id, key, fingerprint, 201, result.model_dump(mode="json"))
        return result


@router.get("/reconcile", response_model=ReconcileOut)
async def reconcile(
    channel_id: uuid.UUID, request: Request, p: View, period: PeriodDep
) -> ReconcileOut:
    """Booked platform sales against payouts, for one outlet (`outlet_id`) and period."""
    outlet_filter(p, period)  # checks the outlet is visible
    async with _db(request, p) as db:
        return await settlements.reconcile(db, period, channel_id)


@router.post("/{settlement_id}/reverse", response_model=SettlementOut)
async def reverse(settlement_id: uuid.UUID, request: Request, p: Manage) -> SettlementOut:
    async with _db(request, p) as db:
        row = await settlements.get(db, settlement_id)
        p.require_outlet(row.outlet_id)
        await settlements.reverse(db, row, p.user_id)
        return SettlementOut.model_validate(row)
