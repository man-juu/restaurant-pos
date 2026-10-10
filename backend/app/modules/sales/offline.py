"""Offline orders (FR-SAL-013, docs/04 section 11). A till that lost its connection keeps
taking orders and uploads each finished one later. The upload replays the normal steps
(create, add lines, send, pay) in one transaction, so stock, journals and the shift are
posted exactly as for an online order. The till's own id makes a repeated upload a no-op.

Nothing taken offline is thrown away: a line that no longer fits (item removed, no price)
is skipped and counted, and a payment that no longer fits (prices or the shift changed)
leaves the order open with the reason, for the cashier to settle by hand."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError
from app.core.settings import service as settings
from app.core.settings.schemas import (
    PaymentMethodSettings,
    PosSettings,
    ServiceChargeSettings,
    TaxSettings,
)
from app.modules.catalog.interface import channel_code
from app.modules.sales import orders, payments
from app.modules.sales.models import PosOrder
from app.modules.sales.offline_schemas import OfflineOrderIn, OfflinePackOut, OfflineSyncOut
from app.modules.sales.pos_schemas import PosOrderCreateIn

MAX_AGE = timedelta(days=7)  # older than this is a till clock or a lost device, not a sale
CLOCK_SLACK = timedelta(minutes=10)


async def pack(db: AsyncSession, tenant_id: uuid.UUID, channel_id: uuid.UUID) -> OfflinePackOut:
    pos = cast(PosSettings, await settings.get_setting(db, tenant_id, "pos"))
    methods = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    return OfflinePackOut(
        enabled=pos.offline_enabled,
        channel_code=await channel_code(db, channel_id),
        tax=cast(TaxSettings, await settings.get_setting(db, tenant_id, "tax")),
        service_charge=cast(
            ServiceChargeSettings, await settings.get_setting(db, tenant_id, "service_charge")
        ),
        cash_rounding_step=pos.cash_rounding_step,
        tips_enabled=pos.tips_enabled,
        methods=[m for m in methods.methods if m.active],
    )


def _out(order: PosOrder, skipped: int = 0) -> OfflineSyncOut:
    return OfflineSyncOut(
        client_id=cast(uuid.UUID, order.client_id),
        order_id=order.id,
        number=order.number,
        status=order.status,  # type: ignore[arg-type]
        problem=order.sync_problem,
        skipped_lines=skipped,
    )


async def _add_lines(
    db: AsyncSession, order: PosOrder, user_id: uuid.UUID, data: OfflineOrderIn
) -> int:
    skipped = 0
    for line in data.lines:
        try:
            async with db.begin_nested():
                await orders.add_line(db, order, user_id=user_id, data=line, served=True)
        except AppError:
            skipped += 1
            await db.refresh(order)
    return skipped


async def _try_pay(
    db: AsyncSession, order: PosOrder, user_id: uuid.UUID, data: OfflineOrderIn
) -> None:
    if data.payment is None:
        return
    try:
        async with db.begin_nested():
            await payments.pay(db, order, user_id=user_id, data=data.payment, language="en")
    except AppError as e:
        await db.refresh(order)  # the savepoint rollback expired it
        order.sync_problem = e.code
        await db.flush()


async def sync(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: OfflineOrderIn
) -> OfflineSyncOut:
    done = await db.scalar(select(PosOrder).where(PosOrder.client_id == data.client_id))
    if done is not None:
        return _out(done)
    pos = cast(PosSettings, await settings.get_setting(db, tenant_id, "pos"))
    if not pos.offline_enabled:
        raise ConflictError("offline_disabled")
    now = datetime.now(UTC)
    if not now - MAX_AGE <= data.taken_at <= now + CLOCK_SLACK:
        raise ConflictError("offline_taken_at")
    order = await orders.create_order(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        data=PosOrderCreateIn(
            outlet_id=data.outlet_id,
            channel_id=data.channel_id,
            label=data.label,
            note=data.note,
        ),
    )
    order.client_id, order.taken_at = data.client_id, data.taken_at
    skipped = await _add_lines(db, order, user_id, data)
    if skipped == len(data.lines):
        order.sync_problem = "no_lines"
    else:
        await orders.send(db, order, user_id)
        await _try_pay(db, order, user_id, data)
    if skipped and order.sync_problem is None:
        order.sync_problem = "lines_skipped"
    await db.flush()
    return _out(order, skipped)
