"""Daily sales endpoints (FR-SAL-002, 003). Outlet scope on every call; costs need
catalog.cost.view (docs/03 rule 5)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW
from app.modules.inventory.interface import visible_outlet
from app.modules.sales import permissions as perm
from app.modules.sales import queries, service
from app.modules.sales.schemas import DayEntryIn, DayOut

router = APIRouter(prefix="/api/v1/sales/days", tags=["sales"])

View = Annotated[Principal, Depends(require(perm.DAY_VIEW))]
Enter = Annotated[Principal, Depends(require(perm.DAY_ENTER))]
Lock = Annotated[Principal, Depends(require(perm.DAY_LOCK))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Lang = Literal["en", "id"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _day(db, p: Principal, outlet_id: uuid.UUID, on: date, lang: str) -> DayOut:  # type: ignore[no-untyped-def]
    return await queries.day_out(
        db, p.tenant_id, outlet_id, on, language=lang, show_cost=p.can(COST_VIEW)
    )


@router.get("/{outlet_id}/{on}", response_model=DayOut)
async def get_day(
    outlet_id: uuid.UUID, on: date, request: Request, p: View, lang: Lang = "en"
) -> DayOut:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, outlet_id)  # another tenant's outlet does not exist here
        return await _day(db, p, outlet_id, on, lang)


@router.post("/entries", response_model=DayOut, status_code=201)
async def enter(
    body: DayEntryIn, request: Request, p: Enter, key: Key, lang: Lang = "en"
) -> DayOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        await service.enter_day(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await _day(db, p, body.outlet_id, body.business_date, lang)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/{outlet_id}/{on}/lock", response_model=DayOut)
async def lock_day(outlet_id: uuid.UUID, on: date, request: Request, p: Lock) -> DayOut:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await service.set_lock(
            db, tenant_id=p.tenant_id, user_id=p.user_id, outlet_id=outlet_id, on=on, locked=True
        )
        return await _day(db, p, outlet_id, on, "en")


@router.post("/{outlet_id}/{on}/reopen", response_model=DayOut)
async def reopen_day(outlet_id: uuid.UUID, on: date, request: Request, p: Lock) -> DayOut:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await service.set_lock(
            db, tenant_id=p.tenant_id, user_id=p.user_id, outlet_id=outlet_id, on=on, locked=False
        )
        return await _day(db, p, outlet_id, on, "en")
