"""Public booking page and reminders (FR-TBL-010).

A manager creates a link per outlet. The link carries a random token; only its SHA-256 is
stored. The page has no sign-in, so the server finds the tenant from the token through one
narrow SECURITY DEFINER function (`booking_link_target`), then works inside a normal tenant
transaction with RLS like any other request. The guest never sends a tenant or outlet ID.

Abuse limits: bookings per IP per hour (throttle table), open online bookings per phone
(setting), party size, how far ahead and the opening hours (settings). Online bookings start
as "pending"; staff confirm them. Tables are picked by the same rule as staff suggestions.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import audit
from app.core.access.subscription import WRITE_BLOCKED, SubscriptionInfo, effective_state
from app.core.customers import service as customers
from app.core.errors import ConflictError, NotFoundError
from app.core.identity import service as identity
from app.core.models import Outlet, OutletModuleOff, Subscription, Tenant, TenantModule
from app.core.settings import service as settings
from app.core.settings.schemas import BookingSettings
from app.modules.tables import bookings
from app.modules.tables.booking_models import HOLDING, BookingLink, Reservation, ReservationTable
from app.modules.tables.booking_schemas import Guest, ReservationIn
from app.modules.tables.models import DiningTable
from app.modules.tables.online_schemas import OnlineIn

PER_IP_HOUR = 10  # bookings from one address per hour, before short lockouts start
_TARGET = text("SELECT tenant_id, outlet_id FROM booking_link_target(:h)")


@dataclass(frozen=True)
class Target:
    tenant_id: uuid.UUID
    outlet_id: uuid.UUID


async def conf(db: AsyncSession, tenant_id: uuid.UUID) -> BookingSettings:
    return cast(BookingSettings, await settings.get_setting(db, tenant_id, "booking"))


async def create_link(
    db: AsyncSession, *, tenant_id: uuid.UUID, outlet_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[BookingLink, str]:
    token = secrets.token_urlsafe(18)
    row = BookingLink(
        tenant_id=tenant_id,
        outlet_id=outlet_id,
        token_hash=identity.hash_token(token),
        token_hint=token[-4:],
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    await _audit_link(db, row, user_id, "create")
    return row, token


async def links(db: AsyncSession, outlet_id: uuid.UUID) -> list[BookingLink]:
    stmt = (
        select(BookingLink)
        .where(BookingLink.outlet_id == outlet_id)
        .order_by(BookingLink.created_at.desc())
        .limit(50)
    )
    return list(await db.scalars(stmt))


async def get_link(db: AsyncSession, link_id: uuid.UUID) -> BookingLink:
    row = await db.get(BookingLink, link_id, with_for_update=True)
    if row is None:
        raise NotFoundError("booking_link_not_found")
    return row


async def disable_link(db: AsyncSession, row: BookingLink, user_id: uuid.UUID) -> None:
    if row.disabled_at is None:
        row.disabled_at = datetime.now(UTC)
        await db.flush()
        await _audit_link(db, row, user_id, "disable")


async def _audit_link(db: AsyncSession, row: BookingLink, user_id: uuid.UUID, verb: str) -> None:
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=user_id,
        outlet_id=row.outlet_id,
        action=f"tables.booking_link.{verb}",
        target_type="booking_link",
        target_id=row.id,
        summary={"hint": row.token_hint},
    )


async def target(sessions: async_sessionmaker[AsyncSession], token: str) -> Target:
    """The outlet behind a link token; 404 for unknown, switched-off or malformed tokens."""
    if not 16 <= len(token) <= 64:
        raise NotFoundError("booking_closed")
    async with sessions() as db, db.begin():
        row = (await db.execute(_TARGET, {"h": identity.hash_token(token)})).one_or_none()
    if row is None:
        raise NotFoundError("booking_closed")
    return Target(tenant_id=row.tenant_id, outlet_id=row.outlet_id)


async def open_outlet(db: AsyncSession, t: Target, *, write: bool) -> Outlet:
    """The same gates a signed-in request passes: subscription, module on, outlet active.
    Every failure looks the same to the guest (the page is simply closed)."""
    outlet = await db.get(Outlet, t.outlet_id)
    module_on = await db.scalar(select(TenantModule.enabled).where(TenantModule.module == "tables"))
    off = await db.scalar(
        select(func.count())
        .select_from(OutletModuleOff)
        .where(OutletModuleOff.outlet_id == t.outlet_id, OutletModuleOff.module == "tables")
    )
    state = effective_state(await _subscription(db), datetime.now(UTC))
    blocked = state == "suspended" or (write and state in WRITE_BLOCKED)
    if outlet is None or not outlet.is_active or not module_on or off or blocked:
        raise NotFoundError("booking_closed")
    return outlet


async def _subscription(db: AsyncSession) -> SubscriptionInfo | None:
    s = await db.scalar(select(Subscription))
    if s is None:
        return None
    return SubscriptionInfo(
        plan_type=s.plan_type,
        ends_at=s.ends_at,
        grace_days=s.grace_days,
        reminders_enabled=s.reminders_enabled,
        reminder_days=tuple(s.reminder_days or ()),
        suspended=s.suspended,
    )


async def tenant_name(db: AsyncSession) -> str:
    return await db.scalar(select(Tenant.name)) or ""


def _starts(c: BookingSettings, day: date, tz: ZoneInfo, now: datetime) -> list[datetime]:
    """Bookable start times of one day: inside opening hours, after the notice period, not
    beyond `days_ahead`."""
    today = now.astimezone(tz).date()
    if not today <= day <= today + timedelta(days=c.days_ahead):
        return []
    midnight = datetime.combine(day, time(0), tzinfo=tz)
    earliest = now + timedelta(minutes=c.min_notice_minutes)
    times = (
        midnight + timedelta(minutes=m)
        for m in range(c.opens_min, c.closes_min + 1, c.slot_minutes)
    )
    return [s for s in times if s >= earliest]


async def slots(
    db: AsyncSession, t: Target, outlet: Outlet, day: date, party: int
) -> list[datetime]:
    """Start times on `day` with a free table (or pair) for the party. Two queries for the
    whole day, not one per time."""
    c = await conf(db, t.tenant_id)
    starts = _starts(c, day, ZoneInfo(outlet.timezone), datetime.now(UTC))
    if party > c.max_party or not starts:
        return []
    dwell = timedelta(minutes=(await bookings.rules(db, t.tenant_id)).default_dwell_minutes)
    tables = list(
        await db.scalars(
            select(DiningTable).where(DiningTable.outlet_id == outlet.id, DiningTable.is_active)
        )
    )
    holds = await _holds(db, {x.id for x in tables}, starts[0], starts[-1] + dwell)

    def free_at(s: datetime) -> list[DiningTable]:
        return [
            x for x in tables if not any(a < s + dwell and b > s for a, b in holds.get(x.id, []))
        ]

    return [s for s in starts if bookings.options(free_at(s), party)]


async def _holds(
    db: AsyncSession, table_ids: set[uuid.UUID], start: datetime, end: datetime
) -> dict[uuid.UUID, list[tuple[datetime, datetime]]]:
    ends = Reservation.starts_at + func.make_interval(0, 0, 0, 0, 0, Reservation.duration_min)
    rows = await db.execute(
        select(ReservationTable.table_id, Reservation.starts_at, ends)
        .join(Reservation, Reservation.id == ReservationTable.reservation_id)
        .where(
            ReservationTable.table_id.in_(table_ids),
            Reservation.status.in_(HOLDING),
            Reservation.starts_at < end,
            ends > start,
        )
    )
    out: dict[uuid.UUID, list[tuple[datetime, datetime]]] = {}
    for table_id, a, b in rows.all():
        out.setdefault(table_id, []).append((a, b))
    return out


async def throttle(sessions: async_sessionmaker[AsyncSession], ip: str | None) -> None:
    """Count one booking attempt for this address in the current hour; 429-style refusal
    (as a conflict) once over the limit. The key holds a hash, never the IP itself."""
    if ip is None:
        return
    hour = datetime.now(UTC).strftime("%Y%m%d%H")
    key = identity.throttle_key("book", f"{ip}|{hour}")
    async with sessions() as db, db.begin():
        if await identity.locked_until(db, [key]):
            raise ConflictError("too_many_attempts")
        await identity.record_failure(db, [key], PER_IP_HOUR)


async def book(db: AsyncSession, t: Target, outlet: Outlet, data: OnlineIn) -> Reservation:
    c = await conf(db, t.tenant_id)
    local = data.starts_at.astimezone(ZoneInfo(outlet.timezone))
    # Also refuses a party too big, too soon, too far ahead or outside opening hours.
    if data.starts_at not in await slots(db, t, outlet, local.date(), data.party_size):
        raise ConflictError("slot_not_available")
    guest = await customers.by_phone(db, data.phone) or await customers.save(
        db, tenant_id=t.tenant_id, user_id=None, name=data.name, phone=data.phone, consent=True
    )
    if await _open_count(db, guest.id) >= c.max_open_per_phone:
        raise ConflictError("too_many_bookings")
    choice = await bookings.suggest(
        db,
        outlet.id,
        data.starts_at,
        (await bookings.rules(db, t.tenant_id)).default_dwell_minutes,
        data.party_size,
    )
    if not choice:
        raise ConflictError("slot_not_available")
    return await bookings.book(
        db,
        tenant_id=t.tenant_id,
        user_id=None,
        source="online",
        data=ReservationIn(
            outlet_id=outlet.id,
            guest=Guest(customer_id=guest.id),
            party_size=data.party_size,
            starts_at=data.starts_at,
            table_ids=choice[0].table_ids,
            notes=data.notes,
        ),
    )


async def _open_count(db: AsyncSession, customer_id: uuid.UUID) -> int:
    stmt = select(func.count()).where(
        Reservation.customer_id == customer_id,
        Reservation.source == "online",
        Reservation.status.in_(("pending", "confirmed")),
        Reservation.starts_at >= datetime.now(UTC),
    )
    return int(await db.scalar(stmt) or 0)


def reminder_text(template: str, values: dict[str, str]) -> str:
    """Fills {name}, {outlet}, {date}, {time} and {party}. Plain replacement, not
    str.format: a template typed by a user must not reach Python's format machinery."""
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


async def remind(
    db: AsyncSession, r: Reservation, outlet: Outlet, user_id: uuid.UUID
) -> tuple[str, str | None]:
    """The reminder message and the guest's phone; staff send it from their own WhatsApp
    or SMS (no messaging API, ADR 0.81). Records that a reminder went out."""
    c = await conf(db, r.tenant_id)
    guest = await customers.get(db, r.customer_id)
    local = r.starts_at.astimezone(ZoneInfo(outlet.timezone))
    message = reminder_text(
        c.reminder_text,
        {
            "name": guest.name,
            "outlet": outlet.name,
            "date": local.strftime("%d/%m/%Y"),
            "time": local.strftime("%H:%M"),
            "party": str(r.party_size),
        },
    )
    r.reminded_at = datetime.now(UTC)
    await db.flush()
    await audit.record(
        db,
        tenant_id=r.tenant_id,
        user_id=user_id,
        outlet_id=r.outlet_id,
        action="tables.reservation.remind",
        target_type="reservation",
        target_id=r.id,
        summary={},
    )
    return message, guest.phone
