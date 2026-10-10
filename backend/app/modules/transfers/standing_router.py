"""Standing transfer orders (FR-TRF-005) and internal transfer charges (FR-TRF-006). The
receiving outlet owns its standing orders; either side may read them."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select

from app.core.access.policy import PermissionDenied, Principal, require
from app.core.errors import NotFoundError
from app.core.reports import PeriodDep
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW, tenant_today
from app.modules.transfers import permissions as perm
from app.modules.transfers import standing
from app.modules.transfers.models import Transfer
from app.modules.transfers.standing_models import StandingTransfer
from app.modules.transfers.standing_schemas import ChargeRow, StandingIn, StandingOut

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])

View = Annotated[Principal, Depends(require(perm.VIEW))]
Ask = Annotated[Principal, Depends(require(perm.REQUEST))]
Lang = Literal["en", "id"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/standing", response_model=list[StandingOut])
async def list_standing(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[StandingOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        today = await tenant_today(db, p.tenant_id)
        rows = await db.scalars(
            select(StandingTransfer)
            .where(
                or_(
                    StandingTransfer.to_outlet_id == outlet_id,
                    StandingTransfer.from_outlet_id == outlet_id,
                )
            )
            .order_by(StandingTransfer.created_at)
        )
        return [await standing.out(db, s, today, lang) for s in rows]


@router.post("/standing", response_model=StandingOut, status_code=201)
async def create_standing(body: StandingIn, request: Request, p: Ask) -> StandingOut:
    p.require_outlet(body.to_outlet_id)
    async with _db(request, p) as db:
        row = await standing.save(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await standing.out(db, row, await tenant_today(db, p.tenant_id))


@router.put("/standing/{standing_id}", response_model=StandingOut)
async def update_standing(
    standing_id: uuid.UUID, body: StandingIn, request: Request, p: Ask
) -> StandingOut:
    p.require_outlet(body.to_outlet_id)
    async with _db(request, p) as db:
        row = await db.get(StandingTransfer, standing_id, with_for_update=True)
        if row is None or not p.can_access_outlet(row.to_outlet_id):
            raise NotFoundError("standing_not_found")
        await standing.save(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, row=row)
        return await standing.out(db, row, await tenant_today(db, p.tenant_id))


@router.post("/standing/run")
async def run_standing(request: Request, p: Ask) -> dict[str, int]:
    """Make the requests that are due now, without waiting for the worker (it runs every
    10 minutes and never makes one twice)."""
    async with _db(request, p) as db:
        return {"made": await standing.run(db, p.tenant_id, p.can_access_outlet)}


@router.get("/reports/charges", response_model=list[ChargeRow])
async def charges(request: Request, p: View, period: PeriodDep) -> list[ChargeRow]:
    """FR-TRF-006: shipped transfers in the period per pair of outlets, at cost and charged.
    Shows stock values, so it also needs catalog.cost.view."""
    if not p.can(COST_VIEW):
        raise PermissionDenied(details={"permission": COST_VIEW})
    t = Transfer
    stmt = (
        select(
            t.from_outlet_id,
            t.to_outlet_id,
            func.count(t.id),
            func.sum(t.shipped_value),
            func.sum(t.charge_total),
        )
        .where(
            t.status.in_(("shipped", "received")),
            t.shipped_on >= period.date_from,
            t.shipped_on <= period.date_to,
        )
        .group_by(t.from_outlet_id, t.to_outlet_id)
    )
    if not p.all_outlets:
        mine = sorted(p.outlet_ids)
        stmt = stmt.where(or_(t.from_outlet_id.in_(mine), t.to_outlet_id.in_(mine)))
    async with _db(request, p) as db:
        rows = (await db.execute(stmt)).all()
    return [
        ChargeRow(from_outlet_id=a, to_outlet_id=b, transfers=n, cost=int(c), charge=int(ch))
        for a, b, n, c, ch in rows
    ]
