"""Walk-in waitlist (FR-TBL-008).

Estimated wait for a party: the tables big enough for it, each free now or expected free at
its session's start plus the dwell time; the parties ahead in the queue that fit the same
tables take the earliest ones first. A rough, honest guide, shown in whole minutes."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.customers.models import Customer
from app.core.errors import ConflictError, NotFoundError
from app.modules.tables.booking_models import WaitlistEntry
from app.modules.tables.booking_schemas import WaitOut
from app.modules.tables.bookings import rules, seat_at
from app.modules.tables.models import DiningTable, SessionTable, TableSession


async def _free_times(
    db: AsyncSession, outlet_id: uuid.UUID, dwell: int, now: datetime
) -> list[tuple[int, datetime]]:
    """(capacity, expected free time) for every active table of the outlet."""
    tables = list(
        await db.scalars(
            select(DiningTable).where(DiningTable.outlet_id == outlet_id, DiningTable.is_active)
        )
    )
    opened = dict(
        (
            await db.execute(
                select(SessionTable.table_id, TableSession.opened_at)
                .join(TableSession, TableSession.id == SessionTable.session_id)
                .where(SessionTable.active, TableSession.status == "open")
            )
        ).all()
    )
    soon = now + timedelta(minutes=5)  # a table being cleaned, or a party past its time
    out = []
    for t in tables:
        start = opened.get(t.id)
        if start is not None:
            out.append((t.capacity, max(start + timedelta(minutes=dwell), soon)))
        else:
            out.append((t.capacity, soon if t.status == "needs_cleaning" else now))
    return out


def estimate(
    party: int, ahead: list[int], slots: list[tuple[int, datetime]], now: datetime, dwell: int
) -> int:
    """Minutes until a table that fits `party` is likely free, after the parties `ahead`."""
    fits = sorted(free for cap, free in slots if cap >= party)
    if not fits:
        return dwell  # no single table is big enough: tables must be joined; a guess
    biggest = max(cap for cap, _ in slots if cap >= party)
    queue = sum(1 for p in ahead if p <= biggest)  # parties ahead that compete for them
    rounds, index = divmod(queue, len(fits))
    when = fits[index] + timedelta(minutes=dwell * rounds)
    return max(int((when - now).total_seconds() // 60), 0)


async def add(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    outlet_id: uuid.UUID,
    customer: Customer,
    party: int,
) -> WaitlistEntry:
    row = WaitlistEntry(
        tenant_id=tenant_id,
        outlet_id=outlet_id,
        customer_id=customer.id,
        party_size=party,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    await _audit(db, row, user_id, "add")
    return row


async def _audit(db: AsyncSession, w: WaitlistEntry, user_id: uuid.UUID, verb: str) -> None:
    await audit.record(
        db,
        tenant_id=w.tenant_id,
        user_id=user_id,
        outlet_id=w.outlet_id,
        action=f"tables.waitlist.{verb}",
        target_type="waitlist_entry",
        target_id=w.id,
        summary={"party": w.party_size},
    )


async def get(db: AsyncSession, entry_id: uuid.UUID) -> WaitlistEntry:
    row = await db.get(WaitlistEntry, entry_id, with_for_update=True)
    if row is None:
        raise NotFoundError("waitlist_entry_not_found")
    return row


async def seat(
    db: AsyncSession,
    w: WaitlistEntry,
    tables: list[DiningTable],
    *,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
) -> None:
    if w.status != "waiting":
        raise ConflictError("wrong_status", details={"status": w.status})
    w.session_id = await seat_at(
        db, tables, user_id=user_id, party_size=w.party_size, channel_id=channel_id
    )
    w.status, w.seated_at = "seated", datetime.now(UTC)
    await db.flush()
    await _audit(db, w, user_id, "seat")


async def leave(db: AsyncSession, w: WaitlistEntry, user_id: uuid.UUID) -> None:
    if w.status != "waiting":
        raise ConflictError("wrong_status", details={"status": w.status})
    w.status = "left"
    await db.flush()
    await _audit(db, w, user_id, "leave")


async def waiting(db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID) -> list[WaitOut]:
    rows = list(
        await db.scalars(
            select(WaitlistEntry)
            .where(WaitlistEntry.outlet_id == outlet_id, WaitlistEntry.status == "waiting")
            .order_by(WaitlistEntry.added_at)
            .limit(200)
        )
    )
    dwell = (await rules(db, tenant_id)).default_dwell_minutes
    now = datetime.now(UTC)
    slots = await _free_times(db, outlet_id, dwell, now)
    who = select(Customer).where(Customer.id.in_({r.customer_id for r in rows}))
    people = {c.id: c for c in await db.scalars(who)}
    return [
        WaitOut(
            id=r.id,
            customer_id=r.customer_id,
            guest_name=people[r.customer_id].name,
            guest_phone=people[r.customer_id].phone,
            party_size=r.party_size,
            status=r.status,
            added_at=r.added_at,
            estimated_wait_min=estimate(
                r.party_size, [x.party_size for x in rows[:i]], slots, now, dwell
            ),
        )
        for i, r in enumerate(rows)
    ]
