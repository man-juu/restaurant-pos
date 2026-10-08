"""Production endpoints (FR-PRD-001 to 004). Outlet scope is checked on every call; an
order in another outlet looks like one that does not exist."""

import uuid
from datetime import date
from typing import Annotated, Literal

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
from app.core.tenancy import tenant_session
from app.modules.production import permissions as perm
from app.modules.production import service
from app.modules.production.models import ProductionOrder
from app.modules.production.schemas import ProductionCompleteIn, ProductionOut, ProductionPlanIn

router = APIRouter(prefix="/api/v1/production/orders", tags=["production"])

View = Annotated[Principal, Depends(require(perm.ORDER_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.ORDER_MANAGE))]
Reverse = Annotated[Principal, Depends(require(perm.ORDER_REVERSE))]
Lang = Literal["en", "id"]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _scoped(db, p: Principal, order_id: uuid.UUID) -> ProductionOrder:  # type: ignore[no-untyped-def]
    order = await service.get_order(db, order_id)
    p.require_outlet(order.outlet_id)
    return order


@router.get("", response_model=list[ProductionOut])
async def list_orders(
    outlet_id: uuid.UUID, request: Request, p: View, on: date | None = None, lang: Lang = "en"
) -> list[ProductionOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = select(ProductionOrder).where(ProductionOrder.outlet_id == outlet_id)
        if on is not None:
            stmt = stmt.where(ProductionOrder.production_date == on)
        stmt = stmt.order_by(ProductionOrder.created_at.desc()).limit(100)
        return [await service.order_out(db, o, lang) for o in await db.scalars(stmt)]


@router.get("/{order_id}", response_model=ProductionOut)
async def get_order(
    order_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> ProductionOut:
    async with _db(request, p) as db:
        return await service.order_out(db, await _scoped(db, p, order_id), lang)


@router.post("", response_model=ProductionOut, status_code=201)
async def plan_order(
    body: ProductionPlanIn, request: Request, p: Manage, key: Key
) -> ProductionOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        order = await service.plan(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await service.order_out(db, order)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/{order_id}/complete", response_model=ProductionOut)
async def complete_order(
    order_id: uuid.UUID, body: ProductionCompleteIn, request: Request, p: Manage
) -> ProductionOut:
    async with _db(request, p) as db:
        await _scoped(db, p, order_id)
        order = await service.complete(db, user_id=p.user_id, order_id=order_id, data=body)
        return await service.order_out(db, order)


@router.post("/{order_id}/cancel", response_model=ProductionOut)
async def cancel_order(order_id: uuid.UUID, request: Request, p: Manage) -> ProductionOut:
    async with _db(request, p) as db:
        await _scoped(db, p, order_id)
        order = await service.cancel(db, user_id=p.user_id, order_id=order_id)
        return await service.order_out(db, order)


@router.post("/{order_id}/reverse", response_model=ProductionOut)
async def reverse_order(order_id: uuid.UUID, request: Request, p: Reverse) -> ProductionOut:
    async with _db(request, p) as db:
        await _scoped(db, p, order_id)
        order = await service.reverse_order(db, user_id=p.user_id, order_id=order_id)
        return await service.order_out(db, order)
