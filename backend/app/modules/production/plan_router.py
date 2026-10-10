"""Production plan suggestion (FR-PRD-005). Outlet scope on every call."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.errors import ConflictError
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import tenant_today
from app.modules.production import permissions as perm
from app.modules.production import plan, service
from app.modules.production.schemas import (
    PlanAcceptIn,
    PlanOut,
    ProductionOut,
    ProductionPlanIn,
)

router = APIRouter(prefix="/api/v1/production/plan", tags=["production"])

View = Annotated[Principal, Depends(require(perm.ORDER_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.ORDER_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Lang = Literal["en", "id"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=PlanOut)
async def suggestion(outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en") -> PlanOut:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        today = await tenant_today(db, p.tenant_id)
        days, rows = await plan.suggestion(db, p.tenant_id, outlet_id, today, lang)
        return PlanOut(days=days, rows=rows)


@router.post("/accept", response_model=list[ProductionOut], status_code=201)
async def accept(
    body: PlanAcceptIn, request: Request, p: Manage, key: Key, lang: Lang = "en"
) -> list[ProductionOut] | JSONResponse:
    """One planned production order per chosen line (FR-PRD-001)."""
    p.require_outlet(body.outlet_id)
    if len({ln.item_id for ln in body.lines}) != len(body.lines):
        raise ConflictError("duplicate_item")
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        made = []
        for ln in body.lines:
            data = ProductionPlanIn(
                outlet_id=body.outlet_id,
                item_id=ln.item_id,
                planned_qty=ln.qty,
                production_date=body.production_date,
            )
            order = await service.plan(db, tenant_id=p.tenant_id, user_id=p.user_id, data=data)
            made.append(await service.order_out(db, order, lang, show_cost=False))
        payload = [m.model_dump(mode="json") for m in made]
        await remember(db, p.tenant_id, key, fingerprint, 201, payload)
        return made
