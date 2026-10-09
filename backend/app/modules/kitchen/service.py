"""Kitchen tickets (FR-KDS-001 to 004). Lines sent from the till become tickets, one per
station, in the same transaction as the send (app/core/events.py). Each step locks the
ticket and checks its status, so two screens cannot bump the same ticket twice."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.events import Event
from app.core.models import Tenant
from app.core.settings import service as settings
from app.core.settings.schemas import KitchenSettings
from app.modules.catalog.interface import channel_info, item_categories, item_names
from app.modules.inventory.interface import visible_outlet
from app.modules.kitchen.models import KitchenStation, KitchenTicket, KitchenTicketItem
from app.modules.kitchen.schemas import StationIn, TicketItemOut, TicketOut
from app.modules.sales.interface import LineDetail, line_details

# step -> (statuses it may start from, new status, timestamp column)
STEPS: dict[str, tuple[tuple[str, ...], str, str | None]] = {
    "start": (("new",), "preparing", "started_at"),
    "ready": (("new", "preparing"), "ready", "ready_at"),
    "bump": (("new", "preparing", "ready"), "bumped", "bumped_at"),
    "recall": (("bumped",), "ready", None),
}


def _station_for(stations: list[KitchenStation], category: uuid.UUID | None) -> uuid.UUID | None:
    for s in stations:
        if category is not None and category in (s.category_ids or []):
            return s.id
    default = next((s for s in stations if s.is_default), stations[0] if stations else None)
    return default.id if default else None


async def on_lines_sent(db: AsyncSession, event: Event) -> None:
    ids = [uuid.UUID(str(i)) for i in cast(list[object], event.data["line_ids"])]
    lines = await line_details(db, ids)
    if not lines:
        return
    first = lines[0]
    outlet_id = uuid.UUID(str(event.data["outlet_id"]))
    stations = list(
        await db.scalars(
            select(KitchenStation)
            .where(KitchenStation.outlet_id == outlet_id, KitchenStation.is_active)
            .order_by(KitchenStation.name)
        )
    )
    categories = await item_categories(db, {ln.item_id for ln in lines})
    language = await db.scalar(select(Tenant.language).where(Tenant.id == event.tenant_id))
    names = await item_names(db, event.tenant_id, language or "en", {ln.item_id for ln in lines})
    channel, kind, platform = await channel_info(db, first.channel_id)
    by_station: dict[uuid.UUID | None, list[LineDetail]] = defaultdict(list)
    for ln in lines:
        by_station[_station_for(stations, categories.get(ln.item_id, (None, None))[0])].append(ln)
    for station_id, group in by_station.items():
        ticket = KitchenTicket(
            tenant_id=event.tenant_id,
            outlet_id=outlet_id,
            station_id=station_id,
            order_id=first.order_id,
            order_number=first.order_number,
            label=first.order_label,
            channel_name=channel,
            platform=platform if kind == "platform" else None,
        )
        db.add(ticket)
        await db.flush()
        db.add_all(
            KitchenTicketItem(
                tenant_id=event.tenant_id,
                ticket_id=ticket.id,
                line_id=ln.id,
                name=names[ln.item_id].name if ln.item_id in names else "",
                qty=ln.qty,
                modifiers=", ".join(ln.modifiers) or None,
                note=ln.note,
            )
            for ln in group
        )
    await db.flush()


async def on_lines_voided(db: AsyncSession, event: Event) -> None:
    ids = [uuid.UUID(str(i)) for i in cast(list[object], event.data["line_ids"])]
    if ids:
        await db.execute(
            update(KitchenTicketItem)
            .where(KitchenTicketItem.line_id.in_(ids))
            .values(status="void")
        )


async def save_station(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: StationIn,
    station_id: uuid.UUID | None = None,
) -> KitchenStation:
    await visible_outlet(db, data.outlet_id)
    if station_id is None:
        station = KitchenStation(tenant_id=tenant_id, **data.model_dump())
        db.add(station)
    else:
        found = await db.get(KitchenStation, station_id, with_for_update=True)
        if found is None or found.outlet_id != data.outlet_id:
            raise NotFoundError("station_not_found")
        station = found
        for key, value in data.model_dump().items():
            setattr(station, key, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("station_name_taken") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=station.outlet_id,
        action="kitchen.station.save",
        target_type="kitchen_station",
        target_id=station.id,
        summary={"name": station.name, "categories": len(data.category_ids)},
    )
    return station


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> KitchenTicket:
    ticket = await db.get(KitchenTicket, ticket_id, with_for_update=True)
    if ticket is None:
        raise NotFoundError("ticket_not_found")
    return ticket


async def step(db: AsyncSession, ticket: KitchenTicket, action: str) -> None:
    allowed, status, column = STEPS[action]
    if ticket.status not in allowed:
        raise ConflictError("wrong_status", details={"status": ticket.status})
    now = datetime.now(UTC)
    if action == "recall":
        limits = cast(KitchenSettings, await settings.get_setting(db, ticket.tenant_id, "kitchen"))
        if ticket.bumped_at is None or now - ticket.bumped_at > timedelta(
            minutes=limits.recall_minutes
        ):
            raise ConflictError("recall_too_late")
        ticket.bumped_at = None
    ticket.status = status
    if column:
        setattr(ticket, column, now)
    await db.flush()


async def tickets_out(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    outlet_id: uuid.UUID,
    station_id: uuid.UUID | None,
    bumped: bool,
) -> list[TicketOut]:
    """Open tickets oldest first (or the recently bumped ones, for recall)."""
    limits = cast(KitchenSettings, await settings.get_setting(db, tenant_id, "kitchen"))
    now = datetime.now(UTC)
    stmt = select(KitchenTicket).where(KitchenTicket.outlet_id == outlet_id)
    if bumped:
        since = now - timedelta(minutes=limits.recall_minutes)
        stmt = stmt.where(KitchenTicket.status == "bumped", KitchenTicket.bumped_at >= since)
        stmt = stmt.order_by(KitchenTicket.bumped_at.desc())
    else:
        stmt = stmt.where(KitchenTicket.status != "bumped").order_by(KitchenTicket.created_at)
    if station_id is not None:
        stmt = stmt.where(KitchenTicket.station_id == station_id)
    tickets = list(await db.scalars(stmt.limit(200)))
    items: dict[uuid.UUID, list[TicketItemOut]] = defaultdict(list)
    rows = await db.scalars(
        select(KitchenTicketItem)
        .where(KitchenTicketItem.ticket_id.in_([t.id for t in tickets]))
        .order_by(KitchenTicketItem.id)
    )
    for it in rows:
        items[it.ticket_id].append(TicketItemOut.model_validate(it, from_attributes=True))
    late = timedelta(minutes=limits.late_minutes)
    return [
        TicketOut(
            id=t.id,
            station_id=t.station_id,
            order_id=t.order_id,
            order_number=t.order_number,
            label=t.label,
            channel_name=t.channel_name,
            platform=t.platform,
            status=t.status,  # type: ignore[arg-type]
            created_at=t.created_at,
            ready_at=t.ready_at,
            bumped_at=t.bumped_at,
            late=t.status in ("new", "preparing") and now - t.created_at > late,
            items=items.get(t.id, []),
        )
        for t in tickets
    ]
