"""Standing transfer orders (FR-TRF-005). For every active order and every delivery day
from today to today + lead days, one normal transfer request is made, needed by that day.
The (order, day) pair is unique, so the task can run every few minutes without doubling."""

import uuid
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.interface import item_names, stock_items, tenant_today
from app.modules.inventory.interface import visible_outlet
from app.modules.transfers import service
from app.modules.transfers.models import Transfer
from app.modules.transfers.schemas import RequestLine, TransferRequestIn
from app.modules.transfers.standing_models import StandingTransfer, StandingTransferLine
from app.modules.transfers.standing_schemas import StandingIn, StandingLineOut, StandingOut


def mask(days: list[int]) -> int:
    return sum(1 << d for d in days)


def days_of(bits: int) -> list[int]:
    return [d for d in range(7) if bits & (1 << d)]


def due_days(s: StandingTransfer, today: date) -> list[date]:
    """Delivery days whose request should exist by now."""
    span = (today + timedelta(days=k) for k in range(s.lead_days + 1))
    return [d for d in span if s.weekdays & (1 << d.weekday())]


def next_delivery(s: StandingTransfer, today: date) -> date | None:
    if not s.is_active:
        return None
    week = (today + timedelta(days=k) for k in range(7))
    return next((d for d in week if s.weekdays & (1 << d.weekday())), None)


async def _lines(db: AsyncSession, standing_id: uuid.UUID) -> list[StandingTransferLine]:
    return list(
        await db.scalars(
            select(StandingTransferLine).where(StandingTransferLine.standing_id == standing_id)
        )
    )


async def out(db: AsyncSession, s: StandingTransfer, today: date, lang: str = "en") -> StandingOut:
    lines = await _lines(db, s.id)
    names = await item_names(db, s.tenant_id, lang, {ln.item_id for ln in lines})
    return StandingOut(
        id=s.id,
        from_outlet_id=s.from_outlet_id,
        to_outlet_id=s.to_outlet_id,
        weekdays=days_of(s.weekdays),
        lead_days=s.lead_days,
        is_active=s.is_active,
        note=s.note,
        lines=[
            StandingLineOut(
                item_id=ln.item_id,
                qty=ln.qty,
                name=names[ln.item_id].name if ln.item_id in names else "",
                unit_code=names[ln.item_id].unit_code if ln.item_id in names else "",
            )
            for ln in lines
        ],
        next_delivery=next_delivery(s, today),
    )


async def _check(db: AsyncSession, data: StandingIn) -> None:
    if data.from_outlet_id == data.to_outlet_id:
        raise ConflictError("same_outlet")
    await visible_outlet(db, data.from_outlet_id)
    await visible_outlet(db, data.to_outlet_id)
    ids = {ln.item_id for ln in data.lines}
    items = await stock_items(db, ids)
    if bad := {i for i in ids if i not in items or not items[i].is_stocked}:
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, bad))})


async def save(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: StandingIn,
    row: StandingTransfer | None = None,
) -> StandingTransfer:
    await _check(db, data)
    fields = data.model_dump(exclude={"lines", "weekdays"})
    if row is None:
        row = StandingTransfer(tenant_id=tenant_id, created_by=user_id, **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    row.weekdays = mask(data.weekdays)
    await db.flush()
    await db.execute(delete(StandingTransferLine).where(StandingTransferLine.standing_id == row.id))
    db.add_all(
        StandingTransferLine(
            tenant_id=tenant_id, standing_id=row.id, item_id=ln.item_id, qty=ln.qty
        )
        for ln in data.lines
    )
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=row.to_outlet_id,
        action="transfers.standing.save",
        target_type="standing_transfer",
        target_id=row.id,
        summary={"weekdays": data.weekdays, "lines": len(data.lines), "active": row.is_active},
    )
    return row


async def _made(db: AsyncSession, s: StandingTransfer, days: list[date]) -> set[date]:
    rows = await db.scalars(
        select(Transfer.standing_for).where(
            Transfer.standing_id == s.id, Transfer.standing_for.in_(days)
        )
    )
    return {d for d in rows if d is not None}


async def run(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    outlet_ok: Callable[[uuid.UUID], bool] | None = None,
) -> int:
    """Periodic task: make the requests that are due. Returns how many were made.
    `outlet_ok` limits a manual run to the caller's outlets."""
    today = await tenant_today(db, tenant_id)
    orders = list(await db.scalars(select(StandingTransfer).where(StandingTransfer.is_active)))
    made = 0
    for s in orders:
        if outlet_ok is not None and not outlet_ok(s.to_outlet_id):
            continue
        days = due_days(s, today)
        missing = sorted(set(days) - await _made(db, s, days)) if days else []
        lines = [RequestLine(item_id=ln.item_id, qty=ln.qty) for ln in await _lines(db, s.id)]
        for day in missing:
            data = TransferRequestIn(
                from_outlet_id=s.from_outlet_id,
                to_outlet_id=s.to_outlet_id,
                needed_by=day,
                note=s.note,
                lines=lines,
            )
            t = await service.request(db, tenant_id=tenant_id, user_id=s.created_by, data=data)
            t.standing_id, t.standing_for = s.id, day
            await db.flush()
            made += 1
    return made
