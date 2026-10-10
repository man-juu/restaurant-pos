"""Refunds of paid POS orders (FR-SAL-008, docs/03 section 7 "manager approves after the
order is paid"). A refund is requested with a reason, the way the money goes back and what
happens to the stock; approval rules for "refund" decide who must agree (by default a
manager, never the person who asked). Owners and co-owners refund without approval.

Doing the refund reverses the sale's stock movements (exact opposite values), optionally
writes the same ingredients off as waste (the food was eaten or thrown away), marks the
sales document reversed and the order refunded. Cash refunds come out of a drawer and
lower that shift's expected cash."""

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal
from app.core.approvals import ensure_may_decide, ensure_status, mark_decided, request_approval
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Role
from app.core.settings import service as settings
from app.core.settings.schemas import PaymentMethodSettings
from app.modules.catalog.interface import tenant_today
from app.modules.inventory.interface import Posting, reverse
from app.modules.sales import doc_events
from app.modules.sales.models import (
    Payment,
    PosOrder,
    PosOrderLine,
    SalesDocument,
    SalesRefund,
)
from app.modules.sales.orders import _audit
from app.modules.sales.payments import DOC as SALE_DOC
from app.modules.sales.payments import option_changes, stock_quantities
from app.modules.sales.pos_schemas import RefundIn, RefundOut
from app.modules.sales.service import take_stock
from app.modules.sales.shifts import current_shift

DOC = "pos_refund"
NO_APPROVAL = {"owner", "co_owner"}  # docs/03 matrix: "Void or refund" Y for them


def refund_out(r: SalesRefund) -> RefundOut:
    return RefundOut(
        id=r.id,
        status=r.status,  # type: ignore[arg-type]
        reason=r.reason,
        stock_effect=r.stock_effect,
        amount=r.amount,
        method=r.method_code,
        created_by=r.created_by,
        decided_by=r.decided_by,
    )


async def _method_kind(db: AsyncSession, tenant_id: uuid.UUID, code: str) -> str:
    found = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    for m in found.methods:
        if m.code == code and m.active:
            return m.kind
    raise NotFoundError("payment_method_not_found", details={"method": code})


async def _check_method(db: AsyncSession, order: PosOrder, method: str, *, owner: bool) -> None:
    """Money goes back the way it came (security review 2l): a QRIS sale is not refunded as
    cash from the drawer. Owners may choose another way (a customer without the app)."""
    if owner:
        return
    paid = set(await db.scalars(select(Payment.method_code).where(Payment.order_id == order.id)))
    if method not in paid:
        raise ConflictError("refund_method_mismatch", details={"paid_with": sorted(paid)})


async def _template(db: AsyncSession, role_id: uuid.UUID) -> str | None:
    return cast(str | None, await db.scalar(select(Role.template_key).where(Role.id == role_id)))


async def request_refund(
    db: AsyncSession, order: PosOrder, p: Principal, data: RefundIn
) -> SalesRefund:
    if order.status != "paid" or order.document_id is None:
        raise ConflictError("wrong_status", details={"status": order.status})
    doc = cast(SalesDocument, await db.get(SalesDocument, order.document_id))
    owner = await _template(db, p.role_id) in NO_APPROVAL
    await _check_method(db, order, data.method, owner=owner)
    refund = SalesRefund(
        tenant_id=order.tenant_id,
        order_id=order.id,
        document_id=doc.id,
        outlet_id=order.outlet_id,
        status="requested",
        reason=data.reason,
        stock_effect=data.stock_effect,
        amount=doc.total + doc.rounding + doc.tip,
        method_code=data.method,
        method_kind=await _method_kind(db, order.tenant_id, data.method),
        created_by=p.user_id,
        submitted_at=datetime.now(UTC),
    )
    db.add(refund)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("refund_exists") from None
    await _audit(
        db, order, p.user_id, "refund_request", {"amount": refund.amount, "reason": data.reason}
    )
    if owner:
        await _execute(db, refund, order, p.user_id)
        return refund
    link = f"/pos?refund={refund.id}"
    if not await request_approval(
        db, "refund", refund, refund.amount, number=order.number, link=link
    ):
        await _execute(db, refund, order, p.user_id)
    return refund


async def get_refund(db: AsyncSession, refund_id: uuid.UUID) -> SalesRefund:
    refund = await db.get(SalesRefund, refund_id, with_for_update=True)
    if refund is None:
        raise NotFoundError("refund_not_found")
    return refund


async def decide(db: AsyncSession, refund: SalesRefund, p: Principal, *, approve: bool) -> None:
    ensure_status(refund, "requested")
    roles = await settings.required_approver_roles(
        db, document_type="refund", outlet_id=refund.outlet_id, amount=refund.amount
    )
    await ensure_may_decide(db, refund, roles, user_id=p.user_id, role_id=p.role_id)
    order = cast(PosOrder, await db.get(PosOrder, refund.order_id, with_for_update=True))
    if approve:
        await _execute(db, refund, order, p.user_id)
        return
    mark_decided(refund, "rejected", p.user_id)
    await db.flush()
    await _audit(db, order, p.user_id, "refund_reject", {"amount": refund.amount})


async def _drawer(db: AsyncSession, refund: SalesRefund, user_id: uuid.UUID) -> uuid.UUID | None:
    """Cash comes out of the requester's open drawer, else the approver's."""
    if refund.method_kind != "cash":
        return None
    for who in (refund.created_by, user_id):
        if who is not None and (shift := await current_shift(db, refund.outlet_id, who)):
            return shift.id
    return None


async def _execute(
    db: AsyncSession, refund: SalesRefund, order: PosOrder, user_id: uuid.UUID
) -> None:
    doc = cast(SalesDocument, await db.get(SalesDocument, refund.document_id, with_for_update=True))
    if doc.status != "posted":
        raise ConflictError("wrong_status", details={"status": doc.status})
    today = await tenant_today(db, order.tenant_id)
    back = Posting(order.tenant_id, order.outlet_id, user_id, SALE_DOC, doc.id, today)
    try:
        await reverse(db, back, SALE_DOC, doc.id)
    except ConflictError as err:  # nothing was stocked (untracked items only)
        if err.code != "nothing_to_reverse":
            raise
    waste = 0
    if refund.stock_effect == "waste":
        rows = list(
            await db.scalars(
                select(PosOrderLine).where(
                    PosOrderLine.order_id == order.id, PosOrderLine.status != "void"
                )
            )
        )
        qty = stock_quantities(rows, await option_changes(db, rows))
        p = Posting(order.tenant_id, order.outlet_id, user_id, DOC, refund.id, today)
        waste, _ = await take_stock(db, p, qty, "waste")
    doc.status, order.status = "reversed", "refunded"
    await doc_events.reversed_(db, doc, user_id)
    refund.shift_id = await _drawer(db, refund, user_id)
    mark_decided(refund, "done", user_id)
    await db.flush()
    await _audit(db, order, user_id, "refund", {"amount": refund.amount, "waste_value": waste})
