"""Tables and sessions (FR-TBL-001 to 004). Every change locks the rows it changes and
checks their state, so two waiters cannot seat the same table. Orders are opened and moved
through the sales interface; this module never touches sales tables directly."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.interface import move_lines, open_order, order_states
from app.modules.tables.models import DiningTable, Floor, SessionOrder, SessionTable, TableSession
from app.modules.tables.schemas import (
    FloorIn,
    SeatIn,
    TableBillOut,
    TableIn,
    TableOut,
    TableSessionOut,
)


async def _audit(
    db: AsyncSession,
    row: Floor | DiningTable | TableSession,
    user_id: uuid.UUID,
    action: str,
    summary: dict[str, object],
) -> None:
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=user_id,
        outlet_id=row.outlet_id,
        action=f"tables.{action}",
        target_type=type(row).__tablename__,
        target_id=row.id,
        summary=summary,
    )


async def save_floor(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: FloorIn,
    floor_id: uuid.UUID | None = None,
) -> Floor:
    await visible_outlet(db, data.outlet_id)
    if floor_id is None:
        floor = Floor(tenant_id=tenant_id, **data.model_dump())
        db.add(floor)
    else:
        found = await db.get(Floor, floor_id, with_for_update=True)
        if found is None or found.outlet_id != data.outlet_id:
            raise NotFoundError("floor_not_found")
        floor = found
        for key, value in data.model_dump().items():
            setattr(floor, key, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("floor_name_taken") from None
    await _audit(db, floor, user_id, "floor.save", {"name": floor.name})
    return floor


async def get_floor(db: AsyncSession, floor_id: uuid.UUID) -> Floor:
    floor = await db.get(Floor, floor_id)
    if floor is None:
        raise NotFoundError("floor_not_found")
    return floor


async def save_table(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: TableIn,
    table_id: uuid.UUID | None = None,
) -> DiningTable:
    floor = await get_floor(db, data.floor_id)
    if table_id is None:
        table = DiningTable(tenant_id=tenant_id, outlet_id=floor.outlet_id, **data.model_dump())
        db.add(table)
    else:
        table = await get_table(db, table_id, lock=True)
        if table.outlet_id != floor.outlet_id:
            raise ConflictError("floor_in_other_outlet")
        for key, value in data.model_dump().items():
            setattr(table, key, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("table_name_taken") from None
    await _audit(db, table, user_id, "table.save", {"name": table.name})
    return table


async def get_table(db: AsyncSession, table_id: uuid.UUID, *, lock: bool = False) -> DiningTable:
    table = await db.get(DiningTable, table_id, with_for_update=lock)
    if table is None:
        raise NotFoundError("table_not_found")
    return table


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, *, lock: bool = False
) -> TableSession:
    session = await db.get(TableSession, session_id, with_for_update=lock)
    if session is None:
        raise NotFoundError("session_not_found")
    return session


def _require_open(session: TableSession) -> None:
    if session.status != "open":
        raise ConflictError("wrong_status", details={"status": session.status})


async def seat(
    db: AsyncSession, table: DiningTable, *, user_id: uuid.UUID, data: SeatIn
) -> TableSession:
    """FR-TBL-002: opening a table starts a session with its first order."""
    if not table.is_active or table.status not in ("available", "reserved"):
        raise ConflictError("table_not_free", details={"status": table.status})
    session = TableSession(
        tenant_id=table.tenant_id,
        outlet_id=table.outlet_id,
        channel_id=data.channel_id,
        party_size=data.party_size,
        opened_by=user_id,
    )
    db.add(session)
    await db.flush()
    db.add(SessionTable(tenant_id=table.tenant_id, session_id=session.id, table_id=table.id))
    await add_order(db, session, user_id, label=table.name)
    table.status = "occupied"
    await db.flush()
    await _audit(
        db, session, user_id, "session.open", {"table": table.name, "party": data.party_size}
    )
    return session


async def add_order(
    db: AsyncSession, session: TableSession, user_id: uuid.UUID, label: str | None = None
) -> uuid.UUID:
    """Another bill for the same party (split bill by item, FR-TBL-003)."""
    _require_open(session)
    order = await open_order(
        db,
        tenant_id=session.tenant_id,
        user_id=user_id,
        outlet_id=session.outlet_id,
        channel_id=session.channel_id,
        label=label,
    )
    db.add(SessionOrder(tenant_id=session.tenant_id, session_id=session.id, order_id=order.id))
    await db.flush()
    return order.id


async def _active_tables(db: AsyncSession, session_id: uuid.UUID) -> list[DiningTable]:
    stmt = (
        select(DiningTable)
        .join(SessionTable, SessionTable.table_id == DiningTable.id)
        .where(SessionTable.session_id == session_id, SessionTable.active)
        .order_by(DiningTable.id)
        .with_for_update(of=DiningTable)
    )
    return list(await db.scalars(stmt))


async def move(
    db: AsyncSession, session: TableSession, target: DiningTable, user_id: uuid.UUID
) -> None:
    """FR-TBL-003: the party moves to a free table; the tables they left are free again."""
    _require_open(session)
    if (
        target.outlet_id != session.outlet_id
        or not target.is_active
        or target.status != "available"
    ):
        raise ConflictError("table_not_free", details={"status": target.status})
    left = await _active_tables(db, session.id)
    await db.execute(
        update(SessionTable)
        .where(SessionTable.session_id == session.id, SessionTable.active)
        .values(active=False)
    )
    for table in left:
        table.status = "available"
    existing = await db.get(SessionTable, (session.tenant_id, session.id, target.id))
    if existing:
        existing.active = True
    else:
        db.add(SessionTable(tenant_id=session.tenant_id, session_id=session.id, table_id=target.id))
    target.status = "occupied"
    await db.flush()
    await _audit(db, session, user_id, "session.move", {"to": target.name})


async def merge(
    db: AsyncSession, keep: TableSession, other: TableSession, user_id: uuid.UUID
) -> None:
    """FR-TBL-003: two parties become one; tables and bills of `other` join `keep`."""
    _require_open(keep)
    _require_open(other)
    if keep.id == other.id or keep.outlet_id != other.outlet_id:
        raise ConflictError("sessions_not_compatible")
    tables = [
        t.table_id
        for t in await db.scalars(
            select(SessionTable).where(SessionTable.session_id == other.id, SessionTable.active)
        )
    ]
    orders = list(
        await db.scalars(select(SessionOrder.order_id).where(SessionOrder.session_id == other.id))
    )
    await db.execute(
        update(SessionTable).where(SessionTable.session_id == other.id).values(active=False)
    )
    db.add_all(
        SessionTable(tenant_id=keep.tenant_id, session_id=keep.id, table_id=t) for t in tables
    )
    await db.execute(
        update(SessionOrder).where(SessionOrder.session_id == other.id).values(session_id=keep.id)
    )
    keep.party_size += other.party_size
    other.status, other.closed_at, other.merged_into = "closed", datetime.now(UTC), keep.id
    await db.flush()
    await _audit(db, keep, user_id, "session.merge", {"tables": len(tables), "orders": len(orders)})


async def split(
    db: AsyncSession,
    session: TableSession,
    from_order: uuid.UUID,
    line_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> uuid.UUID:
    """FR-TBL-003 split by item: the chosen lines go to a new bill of the same session."""
    _require_open(session)
    owned = await db.scalar(
        select(SessionOrder.order_id).where(
            SessionOrder.session_id == session.id, SessionOrder.order_id == from_order
        )
    )
    if owned is None:
        raise NotFoundError("order_not_found")
    new_order = await add_order(db, session, user_id)
    await move_lines(
        db, from_order=from_order, to_order=new_order, line_ids=line_ids, user_id=user_id
    )
    return new_order


async def close_if_done(db: AsyncSession, order_id: uuid.UUID) -> None:
    """FR-TBL-002: when the last open bill of a session is paid (or closed), the party has
    left; its tables need cleaning."""
    session_id = await db.scalar(
        select(SessionOrder.session_id).where(SessionOrder.order_id == order_id)
    )
    if session_id is None:
        return
    session = await get_session(db, session_id, lock=True)
    if session.status != "open":
        return
    ids = set(
        await db.scalars(select(SessionOrder.order_id).where(SessionOrder.session_id == session.id))
    )
    if any(s.status == "open" for s in (await order_states(db, ids)).values()):
        return
    for table in await _active_tables(db, session.id):
        table.status = "needs_cleaning"
    await db.execute(
        update(SessionTable).where(SessionTable.session_id == session.id).values(active=False)
    )
    session.status, session.closed_at = "closed", datetime.now(UTC)
    await db.flush()


async def set_status(db: AsyncSession, table: DiningTable, status: str, user_id: uuid.UUID) -> None:
    """Mark clean (available) or reserved; a table with a party at it stays occupied."""
    busy = await db.scalar(
        select(SessionTable.session_id).where(
            SessionTable.table_id == table.id, SessionTable.active
        )
    )
    if busy is not None or table.status == "occupied":
        raise ConflictError("table_occupied")
    table.status = status
    await db.flush()
    await _audit(db, table, user_id, "table.status", {"status": status})


async def sessions_out(
    db: AsyncSession, session_ids: set[uuid.UUID]
) -> dict[uuid.UUID, TableSessionOut]:
    """Sessions with their tables and bills in a fixed number of queries (FR-TBL-004)."""
    sessions = list(await db.scalars(select(TableSession).where(TableSession.id.in_(session_ids))))
    links = (
        await db.execute(
            select(SessionTable.session_id, SessionTable.table_id).where(
                SessionTable.session_id.in_(session_ids), SessionTable.active
            )
        )
    ).all()
    order_links = (
        await db.execute(
            select(SessionOrder.session_id, SessionOrder.order_id).where(
                SessionOrder.session_id.in_(session_ids)
            )
        )
    ).all()
    states = await order_states(db, {o for _, o in order_links})
    out = {}
    for s in sessions:
        bills = [states[o] for sid, o in order_links if sid == s.id and o in states]
        out[s.id] = TableSessionOut(
            id=s.id,
            status=s.status,  # type: ignore[arg-type]
            party_size=s.party_size,
            opened_at=s.opened_at,
            channel_id=s.channel_id,
            table_ids=[t for sid, t in links if sid == s.id],
            orders=[
                TableBillOut(
                    id=b.id, number=b.number, status=b.status, subtotal=b.subtotal, lines=b.lines
                )
                for b in bills
            ],
            open_amount=sum(b.subtotal for b in bills if b.status == "open"),
        )
    return out


async def tables_out(db: AsyncSession, outlet_id: uuid.UUID) -> list[TableOut]:
    tables = list(
        await db.scalars(
            select(DiningTable).where(DiningTable.outlet_id == outlet_id).order_by(DiningTable.name)
        )
    )
    links = dict(
        (
            await db.execute(
                select(SessionTable.table_id, SessionTable.session_id).where(
                    SessionTable.table_id.in_([t.id for t in tables]), SessionTable.active
                )
            )
        ).all()
    )
    sessions = await sessions_out(db, set(links.values()))
    return [
        TableOut(
            id=t.id,
            outlet_id=t.outlet_id,
            floor_id=t.floor_id,
            name=t.name,
            capacity=t.capacity,
            x=t.x,
            y=t.y,
            status=t.status,  # type: ignore[arg-type]
            is_active=t.is_active,
            session=sessions.get(links[t.id]) if t.id in links else None,
        )
        for t in tables
    ]
