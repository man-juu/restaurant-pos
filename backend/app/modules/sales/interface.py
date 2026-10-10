"""What other modules may use from sales (module boundaries, CLAUDE.md rule 4): open POS
orders, read their state and totals, move lines between them, and the events sales
publishes. Callers check their own permissions; outlet scope is checked again here by RLS
and by the caller."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales import orders
from app.modules.sales.doc_events import DocumentMoney, document_money, tenders_of_kind
from app.modules.sales.events import (
    DOCUMENT_POSTED,
    DOCUMENT_REVERSED,
    LINES_SENT,
    LINES_VOIDED,
    ORDER_CLOSED,
    ORDER_PAID,
)
from app.modules.sales.models import PosLineModifier, PosOrder, PosOrderLine
from app.modules.sales.money_reports import PeriodTotals, channel_total, period_totals
from app.modules.sales.pos_schemas import PosOrderCreateIn
from app.modules.sales.wholesale import RECEIVABLE_PAID

__all__ = [
    "DOCUMENT_POSTED",
    "DOCUMENT_REVERSED",
    "LINES_SENT",
    "LINES_VOIDED",
    "ORDER_CLOSED",
    "ORDER_PAID",
    "RECEIVABLE_PAID",
    "DocumentMoney",
    "LineDetail",
    "OrderState",
    "PeriodTotals",
    "channel_total",
    "document_money",
    "line_details",
    "move_lines",
    "open_order",
    "order_states",
    "period_totals",
    "tenders_of_kind",
]


@dataclass(frozen=True)
class OrderState:
    id: uuid.UUID
    number: str
    status: str
    outlet_id: uuid.UUID
    channel_id: uuid.UUID
    subtotal: int  # live lines at their prices (before discount, service and tax)
    lines: int


async def open_order(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    outlet_id: uuid.UUID,
    channel_id: uuid.UUID,
    label: str | None,
) -> OrderState:
    data = PosOrderCreateIn(outlet_id=outlet_id, channel_id=channel_id, label=label)
    order = await orders.create_order(db, tenant_id=tenant_id, user_id=user_id, data=data)
    return OrderState(order.id, order.number, order.status, outlet_id, channel_id, 0, 0)


async def order_states(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, OrderState]:
    """Several orders in three queries (the occupancy view lists every table)."""
    found = list(await db.scalars(select(PosOrder).where(PosOrder.id.in_(ids))))
    lines = list(
        await db.scalars(
            select(PosOrderLine).where(
                PosOrderLine.order_id.in_(ids), PosOrderLine.status != "void"
            )
        )
    )
    deltas: dict[uuid.UUID, int] = {}
    stmt = select(PosLineModifier.line_id, PosLineModifier.price_delta).where(
        PosLineModifier.line_id.in_([ln.id for ln in lines])
    )
    for line_id, delta in (await db.execute(stmt)).all():
        deltas[line_id] = deltas.get(line_id, 0) + delta
    totals: dict[uuid.UUID, int] = {}
    counts: dict[uuid.UUID, int] = {}
    for ln in lines:
        value = orders.line_total(ln.qty, ln.unit_price + deltas.get(ln.id, 0))
        totals[ln.order_id] = totals.get(ln.order_id, 0) + value
        counts[ln.order_id] = counts.get(ln.order_id, 0) + 1
    return {
        o.id: OrderState(
            o.id,
            o.number,
            o.status,
            o.outlet_id,
            o.channel_id,
            totals.get(o.id, 0),
            counts.get(o.id, 0),
        )
        for o in found
    }


async def move_lines(
    db: AsyncSession,
    *,
    from_order: uuid.UUID,
    to_order: uuid.UUID,
    line_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> int:
    first, second = sorted([from_order, to_order])  # lock in id order: no deadlock
    locked = {o: await orders.get_order(db, o, lock=True) for o in (first, second)}
    return await orders.move_lines(db, locked[from_order], locked[to_order], line_ids, user_id)


@dataclass(frozen=True)
class LineDetail:
    id: uuid.UUID
    order_id: uuid.UUID
    order_number: str
    order_label: str | None
    channel_id: uuid.UUID
    item_id: uuid.UUID
    qty: Decimal
    note: str | None
    modifiers: tuple[str, ...]
    status: str


async def line_details(db: AsyncSession, line_ids: list[uuid.UUID]) -> list[LineDetail]:
    """What the kitchen needs to make each line, in two queries."""
    rows = (
        await db.execute(
            select(PosOrderLine, PosOrder.number, PosOrder.label, PosOrder.channel_id)
            .join(PosOrder, PosOrder.id == PosOrderLine.order_id)
            .where(PosOrderLine.id.in_(line_ids))
            .order_by(PosOrderLine.created_at, PosOrderLine.id)
        )
    ).all()
    mods: dict[uuid.UUID, list[str]] = {}
    stmt = select(PosLineModifier.line_id, PosLineModifier.name).where(
        PosLineModifier.line_id.in_(line_ids)
    )
    for line_id, name in (await db.execute(stmt)).all():
        mods.setdefault(line_id, []).append(name)
    return [
        LineDetail(
            ln.id,
            ln.order_id,
            number,
            label,
            channel_id,
            ln.item_id,
            ln.qty,
            ln.note,
            tuple(sorted(mods.get(ln.id, []))),
            ln.status,
        )
        for ln, number, label, channel_id in rows
    ]
