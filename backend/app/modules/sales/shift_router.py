"""Cash shift endpoints (FR-SAL-009). A cashier sees and closes only their own shift; people
with `sales.shift.view` (manager, accountant) see every shift of their outlets and can close
one a cashier forgot (they also need `sales.shift.open`, as managers have). Another person's
shift otherwise looks like one that does not exist."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import tenant_session
from app.modules.sales import permissions as perm
from app.modules.sales import shifts
from app.modules.sales.models import CashShift
from app.modules.sales.pos_schemas import MovementIn, ShiftCloseIn, ShiftOpenIn, ShiftOut

router = APIRouter(prefix="/api/v1/pos/shifts", tags=["pos"])

Open = Annotated[Principal, Depends(require(perm.SHIFT_OPEN))]
Own = Open
Review = Annotated[Principal, Depends(require(perm.SHIFT_VIEW))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _visible(
    db: AsyncSession, p: Principal, shift_id: uuid.UUID, *, lock: bool = False
) -> CashShift:
    shift = await shifts.get_shift(db, shift_id, lock=lock)
    p.require_outlet(shift.outlet_id)
    if shift.cashier_id != p.user_id and not p.can(perm.SHIFT_VIEW):
        raise NotFoundError("shift_not_found")
    return shift


@router.post("", response_model=ShiftOut, status_code=201)
async def open_shift(body: ShiftOpenIn, request: Request, p: Open) -> ShiftOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        shift = await shifts.open_shift(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await shifts.shift_out(db, shift)


@router.get("/current", response_model=ShiftOut | None)
async def current_shift(outlet_id: uuid.UUID, request: Request, p: Open) -> ShiftOut | None:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        shift = await shifts.current_shift(db, outlet_id, p.user_id)
        return await shifts.shift_out(db, shift) if shift else None


@router.get("", response_model=list[ShiftOut])
async def list_shifts(
    outlet_id: uuid.UUID, date_from: date, date_to: date, request: Request, p: Review
) -> list[ShiftOut]:
    p.require_outlet(outlet_id)
    if date_to < date_from or (date_to - date_from).days > 92:
        raise AppError("invalid_range", details={"max_days": 92}, status_code=422)
    async with _db(request, p) as db:
        found = await shifts.list_shifts(db, outlet_id, date_from, date_to)
        return [await shifts.shift_out(db, s) for s in found]


@router.get("/{shift_id}", response_model=ShiftOut)
async def get_shift(shift_id: uuid.UUID, request: Request, p: Own) -> ShiftOut:
    async with _db(request, p) as db:
        return await shifts.shift_out(db, await _visible(db, p, shift_id))


@router.post("/{shift_id}/movements", response_model=ShiftOut)
async def add_movement(shift_id: uuid.UUID, body: MovementIn, request: Request, p: Own) -> ShiftOut:
    async with _db(request, p) as db:
        shift = await _visible(db, p, shift_id, lock=True)
        await shifts.add_movement(db, shift, user_id=p.user_id, data=body)
        return await shifts.shift_out(db, shift)


@router.post("/{shift_id}/close", response_model=ShiftOut)
async def close_shift(
    shift_id: uuid.UUID, body: ShiftCloseIn, request: Request, p: Own
) -> ShiftOut:
    async with _db(request, p) as db:
        shift = await _visible(db, p, shift_id, lock=True)
        await shifts.close_shift(db, shift, user_id=p.user_id, data=body)
        return await shifts.shift_out(db, shift)
