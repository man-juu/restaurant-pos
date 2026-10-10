"""Reservations and the walk-in waitlist (FR-TBL-005 to 008). Outlet scope on every call."""

import uuid
from datetime import date, datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.models import Tenant
from app.core.tenancy import tenant_session
from app.modules.inventory.interface import visible_outlet
from app.modules.tables import bookings, waitlist
from app.modules.tables import permissions as perm
from app.modules.tables.booking_schemas import (
    ReservationIn,
    ReservationOut,
    SeatReservationIn,
    SeatWaitIn,
    StatusIn,
    Suggestion,
    WaitIn,
    WaitOut,
)

router = APIRouter(prefix="/api/v1/bookings", tags=["tables"])

View = Annotated[Principal, Depends(require(perm.TABLE_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.SESSION_MANAGE))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _day_start(db: AsyncSession, tenant_id: uuid.UUID, day: date) -> datetime:
    tz = await db.scalar(select(Tenant.timezone).where(Tenant.id == tenant_id))
    return datetime.combine(day, time(0), tzinfo=ZoneInfo(tz or "UTC"))


async def _one(db: AsyncSession, r_id: uuid.UUID) -> ReservationOut:
    [out] = await bookings.outs(db, [await bookings.get(db, r_id)])
    return out


@router.get("/reservations", response_model=list[ReservationOut])
async def list_day(
    outlet_id: uuid.UUID, day: date, request: Request, p: View
) -> list[ReservationOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await bookings.day(db, outlet_id, await _day_start(db, p.tenant_id, day))


@router.get("/suggest", response_model=list[Suggestion])
async def suggest(
    outlet_id: uuid.UUID,
    starts_at: datetime,
    party_size: Annotated[int, Query(ge=1, le=200)],
    request: Request,
    p: View,
    duration_min: Annotated[int | None, Query(ge=15, le=600)] = None,
) -> list[Suggestion]:
    """FR-TBL-006: tables that are free and big enough for the party at that time."""
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        minutes = duration_min or (await bookings.rules(db, p.tenant_id)).default_dwell_minutes
        return await bookings.suggest(db, outlet_id, starts_at, minutes, party_size)


@router.post("/reservations", response_model=ReservationOut, status_code=201)
async def book(body: ReservationIn, request: Request, p: Manage) -> ReservationOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, body.outlet_id)
        row = await bookings.book(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await _one(db, row.id)


async def _scoped(db: AsyncSession, p: Principal, r_id: uuid.UUID):  # type: ignore[no-untyped-def]
    row = await bookings.get(db, r_id, lock=True)
    p.require_outlet(row.outlet_id)
    return row


@router.put("/reservations/{reservation_id}/status", response_model=ReservationOut)
async def set_status(
    reservation_id: uuid.UUID, body: StatusIn, request: Request, p: Manage
) -> ReservationOut:
    async with _db(request, p) as db:
        await bookings.move(db, await _scoped(db, p, reservation_id), body.status, p.user_id)
        return await _one(db, reservation_id)


@router.post("/reservations/{reservation_id}/seat", response_model=ReservationOut)
async def seat_reservation(
    reservation_id: uuid.UUID, body: SeatReservationIn, request: Request, p: Manage
) -> ReservationOut:
    async with _db(request, p) as db:
        row = await _scoped(db, p, reservation_id)
        await bookings.seat_reservation(db, row, user_id=p.user_id, channel_id=body.channel_id)
        return await _one(db, reservation_id)


@router.get("/waitlist", response_model=list[WaitOut])
async def list_waiting(outlet_id: uuid.UUID, request: Request, p: View) -> list[WaitOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await waitlist.waiting(db, p.tenant_id, outlet_id)


@router.post("/waitlist", response_model=list[WaitOut], status_code=201)
async def add_waiting(body: WaitIn, request: Request, p: Manage) -> list[WaitOut]:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, body.outlet_id)
        who = await bookings.guest(db, p.tenant_id, p.user_id, body.guest)
        await waitlist.add(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            outlet_id=body.outlet_id,
            customer=who,
            party=body.party_size,
        )
        return await waitlist.waiting(db, p.tenant_id, body.outlet_id)


@router.post("/waitlist/{entry_id}/seat", response_model=list[WaitOut])
async def seat_waiting(
    entry_id: uuid.UUID, body: SeatWaitIn, request: Request, p: Manage
) -> list[WaitOut]:
    async with _db(request, p) as db:
        entry = await waitlist.get(db, entry_id)
        p.require_outlet(entry.outlet_id)
        tables = await bookings.load_tables(db, entry.outlet_id, body.table_ids, lock=True)
        await waitlist.seat(db, entry, tables, user_id=p.user_id, channel_id=body.channel_id)
        return await waitlist.waiting(db, p.tenant_id, entry.outlet_id)


@router.post("/waitlist/{entry_id}/leave", response_model=list[WaitOut])
async def leave(entry_id: uuid.UUID, request: Request, p: Manage) -> list[WaitOut]:
    async with _db(request, p) as db:
        entry = await waitlist.get(db, entry_id)
        p.require_outlet(entry.outlet_id)
        await waitlist.leave(db, entry, p.user_id)
        return await waitlist.waiting(db, p.tenant_id, entry.outlet_id)
