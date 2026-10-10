"""Floors, tables and sessions (FR-TBL-001 to 004). Outlet scope on every call: a table
or session of another outlet looks like one that does not exist."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.inventory.interface import visible_outlet
from app.modules.tables import permissions as perm
from app.modules.tables import service
from app.modules.tables.models import Floor, TableSession
from app.modules.tables.schemas import (
    FloorIn,
    FloorOut,
    MergeIn,
    MoveIn,
    SeatIn,
    SplitIn,
    StatusIn,
    TableIn,
    TableOut,
    TableSessionOut,
)

router = APIRouter(prefix="/api/v1/tables", tags=["tables"])
View = Annotated[Principal, Depends(require(perm.TABLE_VIEW))]
Setup = Annotated[Principal, Depends(require(perm.TABLE_SETUP))]
Manage = Annotated[Principal, Depends(require(perm.SESSION_MANAGE))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _session(db: AsyncSession, p: Principal, session_id: uuid.UUID) -> TableSession:
    session = await service.get_session(db, session_id, lock=True)
    p.require_outlet(session.outlet_id)
    return session


async def _session_out(db: AsyncSession, session_id: uuid.UUID) -> TableSessionOut:
    return (await service.sessions_out(db, {session_id}))[session_id]


@router.get("/floors", response_model=list[FloorOut])
async def list_floors(outlet_id: uuid.UUID, request: Request, p: View) -> list[FloorOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(Floor).where(Floor.outlet_id == outlet_id).order_by(Floor.sort_order, Floor.name)
        )
        return [FloorOut.model_validate(f, from_attributes=True) for f in await db.scalars(stmt)]


@router.post("/floors", response_model=FloorOut, status_code=201)
async def create_floor(body: FloorIn, request: Request, p: Setup) -> FloorOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        floor = await service.save_floor(db, p.tenant_id, p.user_id, body)
        return FloorOut.model_validate(floor, from_attributes=True)


@router.put("/floors/{floor_id}", response_model=FloorOut)
async def update_floor(floor_id: uuid.UUID, body: FloorIn, request: Request, p: Setup) -> FloorOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        floor = await service.save_floor(db, p.tenant_id, p.user_id, body, floor_id)
        return FloorOut.model_validate(floor, from_attributes=True)


@router.get("", response_model=list[TableOut])
async def list_tables(outlet_id: uuid.UUID, request: Request, p: View) -> list[TableOut]:
    """FR-TBL-004: every table with its party, time seated and open amount."""
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await visible_outlet(db, outlet_id)
        return await service.tables_out(db, outlet_id)


async def _floor_scope(db: AsyncSession, p: Principal, floor_id: uuid.UUID) -> None:
    p.require_outlet((await service.get_floor(db, floor_id)).outlet_id)


@router.post("", response_model=list[TableOut], status_code=201)
async def create_table(body: TableIn, request: Request, p: Setup) -> list[TableOut]:
    async with _db(request, p) as db:
        await _floor_scope(db, p, body.floor_id)
        table = await service.save_table(db, p.tenant_id, p.user_id, body)
        return await service.tables_out(db, table.outlet_id)


@router.put("/{table_id}", response_model=list[TableOut])
async def update_table(
    table_id: uuid.UUID, body: TableIn, request: Request, p: Setup
) -> list[TableOut]:
    async with _db(request, p) as db:
        await _floor_scope(db, p, body.floor_id)
        table = await service.save_table(db, p.tenant_id, p.user_id, body, table_id)
        return await service.tables_out(db, table.outlet_id)


@router.post("/{table_id}/seat", response_model=TableSessionOut, status_code=201)
async def seat(table_id: uuid.UUID, body: SeatIn, request: Request, p: Manage) -> TableSessionOut:
    async with _db(request, p) as db:
        table = await service.get_table(db, table_id, lock=True)
        p.require_outlet(table.outlet_id)
        session = await service.seat(db, table, user_id=p.user_id, data=body)
        return await _session_out(db, session.id)


@router.put("/{table_id}/status", response_model=list[TableOut])
async def set_status(
    table_id: uuid.UUID, body: StatusIn, request: Request, p: Manage
) -> list[TableOut]:
    async with _db(request, p) as db:
        table = await service.get_table(db, table_id, lock=True)
        p.require_outlet(table.outlet_id)
        await service.set_status(db, table, body.status, p.user_id)
        return await service.tables_out(db, table.outlet_id)


@router.get("/sessions/{session_id}", response_model=TableSessionOut)
async def get_session(session_id: uuid.UUID, request: Request, p: View) -> TableSessionOut:
    async with _db(request, p) as db:
        session = await service.get_session(db, session_id)
        p.require_outlet(session.outlet_id)
        return await _session_out(db, session.id)


@router.post("/sessions/{session_id}/move", response_model=TableSessionOut)
async def move(session_id: uuid.UUID, body: MoveIn, request: Request, p: Manage) -> TableSessionOut:
    async with _db(request, p) as db:
        session = await _session(db, p, session_id)
        target = await service.get_table(db, body.to_table_id, lock=True)
        await service.move(db, session, target, p.user_id)
        return await _session_out(db, session.id)


@router.post("/sessions/{session_id}/merge", response_model=TableSessionOut)
async def merge(
    session_id: uuid.UUID, body: MergeIn, request: Request, p: Manage
) -> TableSessionOut:
    first, second = sorted([session_id, body.session_id])  # lock in id order: no deadlock
    async with _db(request, p) as db:
        locked = {s: await _session(db, p, s) for s in (first, second)}
        await service.merge(db, locked[session_id], locked[body.session_id], p.user_id)
        return await _session_out(db, session_id)


@router.post("/sessions/{session_id}/orders", response_model=TableSessionOut, status_code=201)
async def new_bill(session_id: uuid.UUID, request: Request, p: Manage) -> TableSessionOut:
    async with _db(request, p) as db:
        session = await _session(db, p, session_id)
        await service.add_order(db, session, p.user_id)
        return await _session_out(db, session.id)


@router.post("/sessions/{session_id}/split", response_model=TableSessionOut)
async def split(
    session_id: uuid.UUID, body: SplitIn, request: Request, p: Manage
) -> TableSessionOut:
    async with _db(request, p) as db:
        session = await _session(db, p, session_id)
        await service.split(db, session, body.from_order_id, body.line_ids, p.user_id)
        return await _session_out(db, session.id)
