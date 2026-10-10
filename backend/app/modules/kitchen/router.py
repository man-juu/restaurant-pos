"""Kitchen display endpoints (FR-KDS-001 to 004). Outlet scope on every call."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.inventory.interface import visible_outlet
from app.modules.kitchen import permissions as perm
from app.modules.kitchen import service
from app.modules.kitchen.models import KitchenStation
from app.modules.kitchen.schemas import StationIn, StationOut, TicketOut

router = APIRouter(prefix="/api/v1/kitchen", tags=["kitchen"])
View = Annotated[Principal, Depends(require(perm.TICKET_VIEW))]
Update = Annotated[Principal, Depends(require(perm.TICKET_UPDATE))]
Manage = Annotated[Principal, Depends(require(perm.STATION_MANAGE))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/stations", response_model=list[StationOut])
async def list_stations(outlet_id: uuid.UUID, request: Request, p: View) -> list[StationOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, outlet_id)
        stmt = (
            select(KitchenStation)
            .where(KitchenStation.outlet_id == outlet_id)
            .order_by(KitchenStation.name)
        )
        return [StationOut.model_validate(s, from_attributes=True) for s in await db.scalars(stmt)]


@router.post("/stations", response_model=StationOut, status_code=201)
async def create_station(body: StationIn, request: Request, p: Manage) -> StationOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        station = await service.save_station(db, p.tenant_id, p.user_id, body)
        return StationOut.model_validate(station, from_attributes=True)


@router.put("/stations/{station_id}", response_model=StationOut)
async def update_station(
    station_id: uuid.UUID, body: StationIn, request: Request, p: Manage
) -> StationOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        station = await service.save_station(db, p.tenant_id, p.user_id, body, station_id)
        return StationOut.model_validate(station, from_attributes=True)


@router.get("/tickets", response_model=list[TicketOut])
async def list_tickets(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    station_id: uuid.UUID | None = None,
    bumped: bool = False,
) -> list[TicketOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, outlet_id)
        return await service.tickets_out(db, p.tenant_id, outlet_id, station_id, bumped)


@router.post("/tickets/{ticket_id}/{action}", status_code=204)
async def ticket_step(
    ticket_id: uuid.UUID,
    action: Literal["start", "ready", "bump", "recall"],
    request: Request,
    p: Update,
) -> None:
    async with _db(request, p) as db:
        ticket = await service.get_ticket(db, ticket_id)
        p.require_outlet(ticket.outlet_id)
        await service.step(db, ticket, action)
