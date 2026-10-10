"""Reservations (FR-TBL-005 to 007).

A reservation holds its tables from `starts_at` for `duration_min` (default: the tenant's
dwell time). Booking locks the chosen tables first, then checks for overlapping bookings, so
two people cannot take the same table for the same time. Seating opens a normal table
session; no-shows are counted per guest so staff see them on the next booking."""

import uuid
from datetime import datetime, timedelta
from itertools import combinations
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.customers import service as customers
from app.core.customers.models import Customer
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.schemas import TablesSettings
from app.modules.tables.booking_models import HOLDING, Reservation, ReservationTable
from app.modules.tables.booking_schemas import (
    Guest,
    ReservationIn,
    ReservationOut,
    Suggestion,
)
from app.modules.tables.models import DiningTable, SessionTable
from app.modules.tables.schemas import SeatIn
from app.modules.tables.service import seat

# Who may move a reservation to which status by hand (seating has its own call).
MOVES = {
    "confirmed": ("pending",),
    "cancelled": ("pending", "confirmed"),
    "no_show": ("pending", "confirmed"),
    "completed": ("seated",),
}


async def rules(db: AsyncSession, tenant_id: uuid.UUID) -> TablesSettings:
    return cast(TablesSettings, await settings.get_setting(db, tenant_id, "tables"))


async def guest(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, g: Guest) -> Customer:
    if g.customer_id is not None:
        return await customers.get(db, g.customer_id)
    if not g.name:
        raise ConflictError("guest_name_required")
    return await customers.find_or_create(
        db, tenant_id=tenant_id, user_id=user_id, name=g.name, phone=g.phone
    )


async def load_tables(
    db: AsyncSession, outlet_id: uuid.UUID, ids: list[uuid.UUID], *, lock: bool
) -> list[DiningTable]:
    stmt = select(DiningTable).where(DiningTable.id.in_(ids)).order_by(DiningTable.id)
    rows = list(await db.scalars(stmt.with_for_update() if lock else stmt))
    if len(rows) != len(set(ids)) or any(t.outlet_id != outlet_id or not t.is_active for t in rows):
        raise NotFoundError("table_not_found")
    return rows


async def booked(
    db: AsyncSession,
    table_ids: set[uuid.UUID],
    start: datetime,
    end: datetime,
    skip: uuid.UUID | None = None,
) -> set[uuid.UUID]:
    """Tables among `table_ids` held by another reservation overlapping [start, end)."""
    ends = Reservation.starts_at + func.make_interval(0, 0, 0, 0, 0, Reservation.duration_min)
    stmt = (
        select(ReservationTable.table_id)
        .join(Reservation, Reservation.id == ReservationTable.reservation_id)
        .where(
            ReservationTable.table_id.in_(table_ids),
            Reservation.status.in_(HOLDING),
            Reservation.starts_at < end,
            ends > start,
        )
    )
    if skip is not None:
        stmt = stmt.where(Reservation.id != skip)
    return set(await db.scalars(stmt))


async def book(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    data: ReservationIn,
    source: str = "staff",
) -> Reservation:
    """`user_id` None with source "online": the guest booked on the public page; their
    customer record must already be chosen (`data.guest.customer_id`)."""
    conf = await rules(db, tenant_id)
    duration = data.duration_min or conf.default_dwell_minutes
    tables = await load_tables(db, data.outlet_id, data.table_ids, lock=True)
    if sum(t.capacity for t in tables) < data.party_size:
        raise ConflictError("tables_too_small")
    end = data.starts_at + timedelta(minutes=duration)
    clash = await booked(db, {t.id for t in tables}, data.starts_at, end)
    if clash and not conf.allow_overbooking:
        raise ConflictError("table_already_booked", details={"table_ids": sorted(map(str, clash))})
    who = (
        await customers.get(db, data.guest.customer_id)
        if user_id is None and data.guest.customer_id
        else await guest(db, tenant_id, _staff(user_id), data.guest)
    )
    row = Reservation(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        customer_id=who.id,
        party_size=data.party_size,
        starts_at=data.starts_at,
        duration_min=duration,
        notes=data.notes,
        source=source,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    db.add_all(
        ReservationTable(tenant_id=tenant_id, reservation_id=row.id, table_id=t.id) for t in tables
    )
    await db.flush()
    await _audit(db, row, user_id, "book", {"party": row.party_size, "tables": len(tables)})
    return row


def _staff(user_id: uuid.UUID | None) -> uuid.UUID:
    if user_id is None:
        raise ConflictError("guest_name_required")
    return user_id


async def _audit(
    db: AsyncSession,
    r: Reservation,
    user_id: uuid.UUID | None,
    verb: str,
    extra: dict[str, object],
) -> None:
    await audit.record(
        db,
        tenant_id=r.tenant_id,
        user_id=user_id,
        actor_type="user" if user_id else "guest",
        outlet_id=r.outlet_id,
        action=f"tables.reservation.{verb}",
        target_type="reservation",
        target_id=r.id,
        summary={"starts_at": r.starts_at.isoformat(), **extra},
    )


async def get(db: AsyncSession, reservation_id: uuid.UUID, *, lock: bool = False) -> Reservation:
    row = await db.get(Reservation, reservation_id, with_for_update=lock)
    if row is None:
        raise NotFoundError("reservation_not_found")
    return row


async def move(db: AsyncSession, r: Reservation, status: str, user_id: uuid.UUID) -> None:
    if r.status not in MOVES[status]:
        raise ConflictError("wrong_status", details={"status": r.status})
    r.status = status
    await db.flush()
    await _audit(db, r, user_id, status, {})


async def table_ids(db: AsyncSession, reservation_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(ReservationTable.table_id).where(
        ReservationTable.reservation_id == reservation_id
    )
    return list(await db.scalars(stmt))


async def seat_at(
    db: AsyncSession,
    tables: list[DiningTable],
    *,
    user_id: uuid.UUID,
    party_size: int,
    channel_id: uuid.UUID,
) -> uuid.UUID:
    """One session at all `tables` (the first opens it; the others join, all must be free)."""
    if any(not t.is_active or t.status not in ("available", "reserved") for t in tables):
        raise ConflictError("table_not_free")
    session = await seat(
        db, tables[0], user_id=user_id, data=SeatIn(channel_id=channel_id, party_size=party_size)
    )
    for t in tables[1:]:
        db.add(SessionTable(tenant_id=t.tenant_id, session_id=session.id, table_id=t.id))
        t.status = "occupied"
    await db.flush()
    return session.id


async def seat_reservation(
    db: AsyncSession, r: Reservation, *, user_id: uuid.UUID, channel_id: uuid.UUID
) -> None:
    """FR-TBL-007: seating a reservation opens a table session at its tables."""
    if r.status not in ("pending", "confirmed"):
        raise ConflictError("wrong_status", details={"status": r.status})
    tables = await load_tables(db, r.outlet_id, await table_ids(db, r.id), lock=True)
    r.session_id = await seat_at(
        db, tables, user_id=user_id, party_size=r.party_size, channel_id=channel_id
    )
    r.status = "seated"
    await db.flush()
    await _audit(db, r, user_id, "seat", {})


async def no_shows(db: AsyncSession, customer_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    stmt = (
        select(Reservation.customer_id, func.count())
        .where(Reservation.customer_id.in_(customer_ids), Reservation.status == "no_show")
        .group_by(Reservation.customer_id)
    )
    return {c: int(n) for c, n in (await db.execute(stmt)).all()}


async def day(db: AsyncSession, outlet_id: uuid.UUID, start: datetime) -> list[ReservationOut]:
    """One day of bookings at the outlet (from `start`, 24 hours), soonest first."""
    stmt = (
        select(Reservation)
        .where(
            Reservation.outlet_id == outlet_id,
            Reservation.starts_at >= start,
            Reservation.starts_at < start + timedelta(days=1),
        )
        .order_by(Reservation.starts_at)
        .limit(500)
    )
    rows = list(await db.scalars(stmt))
    return await outs(db, rows)


async def outs(db: AsyncSession, rows: list[Reservation]) -> list[ReservationOut]:
    ids = {r.id for r in rows}
    links = (
        await db.execute(
            select(ReservationTable.reservation_id, ReservationTable.table_id).where(
                ReservationTable.reservation_id.in_(ids)
            )
        )
    ).all()
    who = select(Customer).where(Customer.id.in_({r.customer_id for r in rows}))
    people = {c.id: c for c in await db.scalars(who)}
    counts = await no_shows(db, set(people))
    return [
        ReservationOut(
            id=r.id,
            outlet_id=r.outlet_id,
            customer_id=r.customer_id,
            guest_name=people[r.customer_id].name,
            guest_phone=people[r.customer_id].phone,
            no_shows=counts.get(r.customer_id, 0),
            party_size=r.party_size,
            starts_at=r.starts_at,
            duration_min=r.duration_min,
            status=r.status,
            notes=r.notes,
            table_ids=[t for rid, t in links if rid == r.id],
            session_id=r.session_id,
            source=r.source,
            reminded_at=r.reminded_at,
        )
        for r in rows
    ]


async def suggest(
    db: AsyncSession, outlet_id: uuid.UUID, start: datetime, minutes: int, party: int
) -> list[Suggestion]:
    """FR-TBL-006: free tables for the time, smallest fit first; pairs on one floor if no
    single table is big enough. At most five options."""
    tables = list(
        await db.scalars(
            select(DiningTable).where(DiningTable.outlet_id == outlet_id, DiningTable.is_active)
        )
    )
    taken = await booked(db, {t.id for t in tables}, start, start + timedelta(minutes=minutes))
    return [
        Suggestion(
            table_ids=[t.id for t in o],
            names=[t.name for t in o],
            capacity=sum(t.capacity for t in o),
        )
        for o in options([t for t in tables if t.id not in taken], party)
    ]


def options(free: list[DiningTable], party: int) -> list[list[DiningTable]]:
    """Smallest single table that fits first; else pairs on one floor. At most five."""
    singles = sorted((t for t in free if t.capacity >= party), key=lambda t: t.capacity)
    found = [[t] for t in singles]
    if not found:
        pairs = [
            list(p)
            for p in combinations(free, 2)
            if p[0].floor_id == p[1].floor_id and p[0].capacity + p[1].capacity >= party
        ]
        found = sorted(pairs, key=lambda p: sum(t.capacity for t in p))
    return found[:5]
