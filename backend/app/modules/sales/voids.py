"""Voids before payment (FR-SAL-008): a line already sent to the kitchen, or a whole open
order, is voided with a reason instead of deleted. What was cooked is written off as waste
or not, as the business set (`pos.void_stock_effect`), in the same transaction."""

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import service as settings
from app.core.settings.schemas import PosSettings
from app.modules.catalog.interface import tenant_today
from app.modules.inventory.interface import Posting
from app.modules.sales.discounts import open_line
from app.modules.sales.events import ORDER_CLOSED
from app.modules.sales.models import PosLineModifier, PosOrder, PosOrderLine
from app.modules.sales.orders import _audit, announce, require_open
from app.modules.sales.payments import option_changes, stock_quantities
from app.modules.sales.service import take_stock

DOC = "pos_void"


async def _write_off(
    db: AsyncSession, order: PosOrder, lines: list[PosOrderLine], user_id: uuid.UUID
) -> int:
    """Waste of what the voided lines used, one posting per line (its id is the document)."""
    pos = cast(PosSettings, await settings.get_setting(db, order.tenant_id, "pos"))
    if pos.void_stock_effect != "waste" or not lines:
        return 0
    today = await tenant_today(db, order.tenant_id)
    value = 0
    for line in lines:
        qty = stock_quantities([line], await option_changes(db, [line]))
        p = Posting(order.tenant_id, order.outlet_id, user_id, DOC, line.id, today)
        cost, _ = await take_stock(db, p, qty, "waste")
        value += cost
    return value


def _mark(line: PosOrderLine, reason: str, user_id: uuid.UUID) -> None:
    line.status, line.void_reason, line.voided_by = "void", reason, user_id


async def void_line(
    db: AsyncSession, order: PosOrder, line_id: uuid.UUID, *, user_id: uuid.UUID, reason: str
) -> None:
    require_open(order)
    line = await open_line(db, order, line_id)
    if line.status == "new":
        # Not cooked yet: simply take it off (no reason needed, nothing to write off).
        await db.execute(delete(PosLineModifier).where(PosLineModifier.line_id == line.id))
        await db.delete(line)
        await db.flush()
        return
    _mark(line, reason, user_id)
    await db.flush()
    waste = await _write_off(db, order, [line], user_id)
    await _audit(db, order, user_id, "void_line", {"reason": reason, "waste_value": waste})


async def void_order(db: AsyncSession, order: PosOrder, *, user_id: uuid.UUID, reason: str) -> None:
    """An open order nobody will pay for: every line is voided, cooked ones written off."""
    require_open(order)
    lines = list(
        await db.scalars(
            select(PosOrderLine).where(
                PosOrderLine.order_id == order.id, PosOrderLine.status != "void"
            )
        )
    )
    sent = [ln for ln in lines if ln.status == "sent"]
    for line in lines:
        _mark(line, reason, user_id)
    order.status = "void"
    await db.flush()
    waste = await _write_off(db, order, sent, user_id)
    await _audit(
        db,
        order,
        user_id,
        "void",
        {"reason": reason, "lines": len(lines), "waste_value": waste},
    )
    await announce(db, order, user_id, ORDER_CLOSED)
