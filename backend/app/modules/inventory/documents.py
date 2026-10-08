"""Waste logs (FR-INV-008) and manual adjustments (FR-INV-009).

Waste is posted at once: it records what already happened. Adjustments change stock
without a physical event, so they carry a reason and follow the approval rules: submitting
posts them directly when no rule applies, otherwise an approver posts or rejects them.
"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.modules.inventory import flow, policy
from app.modules.inventory.doc_models import Adjustment, AdjustmentLine, WasteLine, WasteLog
from app.modules.inventory.doc_schemas import AdjustmentIn, WasteIn
from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.service import InLine, OutLine, Posting, consume, receive, reverse


async def _audit(
    db: AsyncSession, doc: WasteLog | Adjustment, user_id: uuid.UUID, action: str, **extra: object
) -> None:
    await audit.record(
        db,
        tenant_id=doc.tenant_id,
        user_id=user_id,
        outlet_id=doc.outlet_id,
        action=f"inventory.{action}",
        target_type=doc.__tablename__,
        target_id=doc.id,
        summary={"number": doc.number, "status": doc.status, **extra},
    )


def _posting(doc: WasteLog | Adjustment, user_id: uuid.UUID | None) -> Posting:
    return Posting(
        doc.tenant_id, doc.outlet_id, user_id, doc.__tablename__, doc.id, doc.business_date
    )


# ─── Waste ────────────────────────────────────────────────────────────────


async def post_waste(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: WasteIn
) -> WasteLog:
    await visible_outlet(db, data.outlet_id)
    base = await flow.to_base(db, ((ln.item_id, ln.unit_id, ln.qty) for ln in data.lines))
    allowed = await policy.negative_allowed(db, tenant_id, "other", confirmed=data.confirm_negative)
    log = WasteLog(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        business_date=data.business_date,
        reason_code=data.reason_code,
        note=data.note,
        created_by=user_id,
        status="posted",
    )
    log.number = await flow.next_number(db, tenant_id, "waste", log)
    db.add(log)
    await db.flush()
    await db.execute(
        insert(WasteLine),
        [{"tenant_id": tenant_id, "waste_id": log.id, **ln.model_dump()} for ln in data.lines],
    )
    lines = [OutLine(item, qty) for item, qty in base.items()]
    await consume(db, _posting(log, user_id), "waste", lines, allow_negative=allowed)
    await _audit(db, log, user_id, "waste.post", reason=data.reason_code)
    return log


async def reverse_waste(db: AsyncSession, *, user_id: uuid.UUID, waste_id: uuid.UUID) -> WasteLog:
    log = await db.get(WasteLog, waste_id, with_for_update=True)
    if log is None:
        raise NotFoundError("document_not_found")
    if log.status != "posted":
        raise ConflictError("nothing_to_reverse")
    await reverse(db, _posting(log, user_id), "waste_logs", log.id)
    log.status = "reversed"
    await _audit(db, log, user_id, "waste.reverse")
    return log


# ─── Adjustments ──────────────────────────────────────────────────────────


async def _write_adjustment_lines(db: AsyncSession, adj: Adjustment, data: AdjustmentIn) -> None:
    await db.execute(delete(AdjustmentLine).where(AdjustmentLine.adjustment_id == adj.id))
    await db.execute(
        insert(AdjustmentLine),
        [
            {"tenant_id": adj.tenant_id, "adjustment_id": adj.id, **ln.model_dump()}
            for ln in data.lines
        ],
    )


async def save_adjustment(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AdjustmentIn,
    adjustment_id: uuid.UUID | None = None,
) -> Adjustment:
    """Create a draft, or replace a draft's content."""
    await visible_outlet(db, data.outlet_id)
    await flow.to_base(db, ((ln.item_id, ln.unit_id, ln.qty) for ln in data.lines))  # check
    fields = data.model_dump(include={"outlet_id", "business_date", "reason_code", "note"})
    if adjustment_id is None:
        adj = Adjustment(tenant_id=tenant_id, created_by=user_id, status="draft", **fields)
        adj.number = await flow.next_number(db, tenant_id, "adjustment", adj)
        db.add(adj)
        await db.flush()
    else:
        adj = await _adjustment(db, adjustment_id)
        flow.ensure_status(adj, "draft")
        for key, value in fields.items():
            setattr(adj, key, value)
    await _write_adjustment_lines(db, adj, data)
    await _audit(db, adj, user_id, "adjustment.save", after=data.model_dump(mode="json"))
    return adj


async def _adjustment(db: AsyncSession, adjustment_id: uuid.UUID) -> Adjustment:
    adj = await db.get(Adjustment, adjustment_id, with_for_update=True)
    if adj is None:
        raise NotFoundError("document_not_found")
    return adj


async def _adjustment_change(db: AsyncSession, adj: Adjustment) -> dict[uuid.UUID, Decimal]:
    lines = (
        await db.execute(select(AdjustmentLine).where(AdjustmentLine.adjustment_id == adj.id))
    ).scalars()
    rows = list(lines)
    return await flow.to_base(db, ((ln.item_id, ln.unit_id, ln.qty) for ln in rows))


async def _post_adjustment(db: AsyncSession, adj: Adjustment, user_id: uuid.UUID) -> None:
    change = await _adjustment_change(db, adj)
    expiry = dict(
        (
            await db.execute(
                select(AdjustmentLine.item_id, AdjustmentLine.expiry_date).where(
                    AdjustmentLine.adjustment_id == adj.id
                )
            )
        ).all()
    )
    costs = await flow.average_costs(db, adj.outlet_id, change)
    p = _posting(adj, user_id)
    gains = [
        InLine(i, q, costs.get(i, Decimal(0)), expiry_date=expiry.get(i))
        for i, q in change.items()
        if q > 0
    ]
    losses = [OutLine(i, -q) for i, q in change.items() if q < 0]
    if gains:
        await receive(db, p, "adjustment", gains)
    if losses:
        allowed = await policy.negative_allowed(db, adj.tenant_id, "other", confirmed=False)
        await consume(db, p, "adjustment", losses, allow_negative=allowed)
    flow.mark_decided(adj, "posted", user_id)


async def post_now(db: AsyncSession, adj: Adjustment, user_id: uuid.UUID) -> None:
    """Post a draft without the approval flow (estimated-item corrections only)."""
    flow.ensure_status(adj, "draft")
    await _post_adjustment(db, adj, user_id)
    await _audit(db, adj, user_id, "adjustment.post_now")


async def submit_adjustment(
    db: AsyncSession, *, user_id: uuid.UUID, adjustment_id: uuid.UUID
) -> Adjustment:
    adj = await _adjustment(db, adjustment_id)
    flow.ensure_status(adj, "draft")
    amount = await flow.value_of(db, adj.outlet_id, await _adjustment_change(db, adj))
    flow.mark_submitted(adj)
    if not await flow.approvers_needed(db, "adjustment", adj, amount):
        await _post_adjustment(db, adj, user_id)  # no rule applies: posted at once
    await _audit(db, adj, user_id, "adjustment.submit", amount=amount)
    return adj


async def decide_adjustment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    approve: bool,
) -> Adjustment:
    adj = await _adjustment(db, adjustment_id)
    flow.ensure_status(adj, "submitted")
    amount = await flow.value_of(db, adj.outlet_id, await _adjustment_change(db, adj))
    roles = await flow.approvers_needed(db, "adjustment", adj, amount)
    await flow.ensure_may_decide(db, adj, roles, user_id=user_id, role_id=role_id)
    if approve:
        await _post_adjustment(db, adj, user_id)
    else:
        flow.mark_decided(adj, "rejected", user_id)
    await _audit(db, adj, user_id, "adjustment.approve" if approve else "adjustment.reject")
    return adj
