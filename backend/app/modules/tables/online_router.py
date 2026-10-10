"""Public booking page (no sign-in) and the staff side: links and reminders (FR-TBL-010).

Public routes are `public()`: they do their own checks. The tenant comes from the link token
on the server (online.target), never from the request body."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, public, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.identity.web import client_info
from app.core.models import Outlet
from app.core.tenancy import tenant_session
from app.modules.inventory.interface import visible_outlet
from app.modules.tables import bookings, online
from app.modules.tables import permissions as perm
from app.modules.tables.booking_models import BookingLink
from app.modules.tables.online_schemas import (
    BookedOut,
    LinkOut,
    NewLinkIn,
    NewLinkOut,
    OnlineIn,
    PageOut,
    ReminderOut,
)

# No sign-in: the token in the path is the only key (FR-TBL-010).
public_router = APIRouter(
    prefix="/api/v1/public/booking", tags=["booking"], dependencies=[Depends(public())]
)
router = APIRouter(prefix="/api/v1/bookings", tags=["tables"])

Setup = Annotated[Principal, Depends(require(perm.TABLE_SETUP))]
Manage = Annotated[Principal, Depends(require(perm.SESSION_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _link(row: BookingLink) -> LinkOut:
    return LinkOut(
        id=row.id,
        outlet_id=row.outlet_id,
        hint=row.token_hint,
        created_at=row.created_at,
        disabled_at=row.disabled_at,
    )


@public_router.get("/{token}", response_model=PageOut)
async def page(token: str, request: Request) -> PageOut:
    t = await online.target(request.app.state.sessionmaker, token)
    async with tenant_session(request.app.state.sessionmaker, t.tenant_id) as db:
        outlet = await online.open_outlet(db, t, write=False)
        c = await online.conf(db, t.tenant_id)
        return PageOut(
            business=await online.tenant_name(db),
            outlet=outlet.name,
            timezone=outlet.timezone,
            max_party=c.max_party,
            days_ahead=c.days_ahead,
        )


@public_router.get("/{token}/slots", response_model=list[datetime])
async def slots(
    token: str, day: date, party_size: Annotated[int, Query(ge=1, le=200)], request: Request
) -> list[datetime]:
    t = await online.target(request.app.state.sessionmaker, token)
    async with tenant_session(request.app.state.sessionmaker, t.tenant_id) as db:
        outlet = await online.open_outlet(db, t, write=False)
        return await online.slots(db, t, outlet, day, party_size)


@public_router.post("/{token}", response_model=BookedOut, status_code=201)
async def book(token: str, body: OnlineIn, request: Request, key: Key) -> Any:
    sessions = request.app.state.sessionmaker
    t = await online.target(sessions, token)
    await online.throttle(sessions, client_info(request)[0])
    fingerprint = await request_fingerprint(request)
    async with tenant_session(sessions, t.tenant_id) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        outlet = await online.open_outlet(db, t, write=True)
        row = await online.book(db, t, outlet, body)
        out = BookedOut(
            id=row.id, starts_at=row.starts_at, party_size=row.party_size, status=row.status
        )
        await remember(db, t.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.get("/links", response_model=list[LinkOut])
async def list_links(outlet_id: uuid.UUID, request: Request, p: Setup) -> list[LinkOut]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return [_link(x) for x in await online.links(db, outlet_id)]


@router.post("/links", response_model=NewLinkOut, status_code=201)
async def create_link(body: NewLinkIn, request: Request, p: Setup) -> NewLinkOut:
    p.require_outlet(body.outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await visible_outlet(db, body.outlet_id)
        row, token = await online.create_link(
            db, tenant_id=p.tenant_id, outlet_id=body.outlet_id, user_id=p.user_id
        )
        return NewLinkOut(**_link(row).model_dump(), token=token)


@router.post("/links/{link_id}/disable", response_model=LinkOut)
async def disable_link(link_id: uuid.UUID, request: Request, p: Setup) -> LinkOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        row = await online.get_link(db, link_id)
        p.require_outlet(row.outlet_id)
        await online.disable_link(db, row, p.user_id)
        return _link(row)


@router.post("/reservations/{reservation_id}/remind", response_model=ReminderOut)
async def remind(reservation_id: uuid.UUID, request: Request, p: Manage) -> ReminderOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        row = await bookings.get(db, reservation_id, lock=True)
        p.require_outlet(row.outlet_id)
        outlet = await db.get(Outlet, row.outlet_id)
        assert outlet is not None  # noqa: S101 - the foreign key guarantees it
        message, phone = await online.remind(db, row, outlet, p.user_id)
        return ReminderOut(message=message, phone=phone)
