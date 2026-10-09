"""Stock counts / opname (FR-INV-007).

Starting a count freezes the system quantity of each item. Counters enter what they find
(in a blind count they never see the frozen number); on submit the differences are valued
and the approval rules decide whether an approver must post them. Posting books each
difference as a count correction: gains at the current average cost, losses through FEFO.
Stock found to be missing is real, so a loss may take the balance below zero.
"""

import uuid
from decimal import Decimal
from typing import cast

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import AppError, NotFoundError
from app.core.notifications.service import notify, recipients
from app.core.settings import service as settings
from app.core.settings.schemas import StockSettings
from app.modules.catalog.interface import COST_VIEW, stock_items
from app.modules.inventory import flow
from app.modules.inventory.doc_models import StockCount, StockCountLine
from app.modules.inventory.doc_schemas import CountedIn, CountIn
from app.modules.inventory.models import StockBalance
from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.service import InLine, OutLine, Posting, StockError, consume, receive


class CountIncomplete(AppError):
    status_code, code = 422, "count_incomplete"


async def _audit(db: AsyncSession, c: StockCount, user_id: uuid.UUID, action: str) -> None:
    await audit.record(
        db,
        tenant_id=c.tenant_id,
        user_id=user_id,
        outlet_id=c.outlet_id,
        action=f"inventory.count.{action}",
        target_type="stock_counts",
        target_id=c.id,
        summary={"number": c.number, "status": c.status},
    )


async def _on_hand(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID] | None
) -> dict[uuid.UUID, Decimal]:
    stmt = (
        select(StockBalance.item_id, func.sum(StockBalance.qty))
        .where(StockBalance.outlet_id == outlet_id)
        .group_by(StockBalance.item_id)
    )
    if ids is None:
        stmt = stmt.having(func.sum(StockBalance.qty) != 0)
    else:
        stmt = stmt.where(StockBalance.item_id.in_(ids))
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def start_count(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: CountIn
) -> StockCount:
    await visible_outlet(db, data.outlet_id)
    ids = set(data.item_ids)
    if data.count_type == "full":
        ids |= set(await _on_hand(db, data.outlet_id, None))
    if not ids:
        raise StockError("items_required")
    found = await stock_items(db, ids)
    if bad := sorted(str(i) for i in ids if i not in found or not found[i].is_stocked):
        raise StockError("invalid_reference", details={"item_ids": bad})
    system = await _on_hand(db, data.outlet_id, ids)
    count = StockCount(
        tenant_id=tenant_id,
        created_by=user_id,
        status="draft",
        **data.model_dump(exclude={"item_ids"}),
    )
    count.number = await flow.next_number(db, tenant_id, "stock_count", count)
    db.add(count)
    await db.flush()
    await db.execute(
        insert(StockCountLine),
        [
            {
                "tenant_id": tenant_id,
                "count_id": count.id,
                "item_id": i,
                "system_qty": system.get(i, Decimal(0)),
            }
            for i in sorted(ids)
        ],
    )
    await _audit(db, count, user_id, "start")
    return count


async def _count(db: AsyncSession, count_id: uuid.UUID) -> StockCount:
    count = await db.get(StockCount, count_id, with_for_update=True)
    if count is None:
        raise NotFoundError("document_not_found")
    return count


async def enter_counted(
    db: AsyncSession, *, user_id: uuid.UUID, count_id: uuid.UUID, data: CountedIn
) -> StockCount:
    count = await _count(db, count_id)
    flow.ensure_status(count, "draft")
    known = set(
        (
            await db.execute(
                select(StockCountLine.item_id).where(StockCountLine.count_id == count_id)
            )
        ).scalars()
    )
    if unknown := sorted(str(ln.item_id) for ln in data.lines if ln.item_id not in known):
        raise StockError("invalid_reference", details={"item_ids": unknown})
    for ln in data.lines:
        await db.execute(
            update(StockCountLine)
            .where(StockCountLine.count_id == count_id, StockCountLine.item_id == ln.item_id)
            .values(counted_qty=ln.counted_qty)
        )
    await _audit(db, count, user_id, "enter")
    return count


async def _variances(db: AsyncSession, count: StockCount) -> dict[uuid.UUID, Decimal]:
    lines = list(
        (
            await db.execute(select(StockCountLine).where(StockCountLine.count_id == count.id))
        ).scalars()
    )
    if any(ln.counted_qty is None for ln in lines):
        raise CountIncomplete()
    return {
        ln.item_id: ln.counted_qty - ln.system_qty
        for ln in lines
        if ln.counted_qty is not None and ln.counted_qty != ln.system_qty
    }


async def _post(db: AsyncSession, count: StockCount, user_id: uuid.UUID) -> None:
    diff = await _variances(db, count)
    costs = await flow.average_costs(db, count.outlet_id, diff)
    p = Posting(
        count.tenant_id, count.outlet_id, user_id, "stock_counts", count.id, count.business_date
    )
    gains = [InLine(i, q, costs.get(i, Decimal(0))) for i, q in diff.items() if q > 0]
    losses = [OutLine(i, -q) for i, q in diff.items() if q < 0]
    if gains:
        await receive(db, p, "count_correction", gains)
    if losses:
        await consume(db, p, "count_correction", losses, allow_negative=True)
    flow.mark_decided(count, "posted", user_id)


async def _big_variance(db: AsyncSession, count: StockCount, amount: int) -> None:
    """FR-INV-012: a count whose difference is worth at least the tenant's threshold."""
    stock = cast(StockSettings, await settings.get_setting(db, count.tenant_id, "stock"))
    if stock.count_variance_alert and amount >= stock.count_variance_alert:
        # The amount is cost data: only members who may see costs (docs/03 rule 5).
        users = await recipients(db, "count_variance", count.outlet_id, COST_VIEW)
        params = {"number": count.number, "amount": amount}
        await notify(db, count.tenant_id, users, "count_variance", params, "/inventory")


async def submit_count(db: AsyncSession, *, user_id: uuid.UUID, count_id: uuid.UUID) -> StockCount:
    count = await _count(db, count_id)
    flow.ensure_status(count, "draft")
    amount = await flow.value_of(db, count.outlet_id, await _variances(db, count))
    flow.mark_submitted(count)
    await _big_variance(db, count, amount)
    if not await flow.request_approval(
        db, "count", count, amount, number=count.number, link="/inventory"
    ):
        await _post(db, count, user_id)
    await _audit(db, count, user_id, "submit")
    return count


async def decide_count(
    db: AsyncSession, *, user_id: uuid.UUID, role_id: uuid.UUID, count_id: uuid.UUID, approve: bool
) -> StockCount:
    count = await _count(db, count_id)
    flow.ensure_status(count, "submitted")
    amount = await flow.value_of(db, count.outlet_id, await _variances(db, count))
    roles = await flow.approvers_needed(db, "count", count, amount)
    await flow.ensure_may_decide(db, count, roles, user_id=user_id, role_id=role_id)
    if approve:
        await _post(db, count, user_id)
    else:
        flow.mark_decided(count, "rejected", user_id)
    await _audit(db, count, user_id, "approve" if approve else "reject")
    return count
