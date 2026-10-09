"""Discounts, voids and refunds on POS orders (FR-SAL-007, 008). Each needs its own
permission; discounts also the role's limit, refunds the approval rules for "refund"."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.idempotency import required_idempotency_key
from app.modules.sales import discounts, refunds, voids
from app.modules.sales import permissions as perm
from app.modules.sales.models import PosOrder, SalesRefund
from app.modules.sales.orders import _audit, lines_of, require_open
from app.modules.sales.pos_router import _db, _keyed, _scoped, full_out
from app.modules.sales.pos_schemas import DiscountIn, PosOrderOut, RefundIn, RefundOut, VoidIn

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])

Discount = Annotated[Principal, Depends(require(perm.DISCOUNT_APPLY))]
Void = Annotated[Principal, Depends(require(perm.ORDER_VOID))]
Refund = Annotated[Principal, Depends(require(perm.ORDER_REFUND))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Lang = Literal["en", "id"]


async def _set_order_discount(
    db: AsyncSession, order: PosOrder, p: Principal, data: DiscountIn | None, lang: str
) -> None:
    require_open(order)
    if data is not None:
        live = [ln for ln in await lines_of(db, order, lang) if ln.status != "void"]
        net = sum(ln.line_total - ln.discount for ln in live)
        discounts.check(net, data, p.limits.get(perm.DISCOUNT_APPLY))
    discounts.apply(order, data, p.user_id)
    await db.flush()
    summary: dict[str, object] = (
        {"kind": data.kind, "value": data.value, "reason": data.reason} if data else {}
    )
    await _audit(db, order, p.user_id, "discount", summary)


async def _set_line_discount(
    db: AsyncSession,
    order: PosOrder,
    line_id: uuid.UUID,
    p: Principal,
    data: DiscountIn | None,
    lang: str,
) -> None:
    require_open(order)
    line = await discounts.open_line(db, order, line_id)
    if data is not None:
        [shown] = [ln for ln in await lines_of(db, order, lang) if ln.id == line.id]
        discounts.check(shown.line_total, data, p.limits.get(perm.DISCOUNT_APPLY))
    discounts.apply(line, data, p.user_id)
    await db.flush()
    summary: dict[str, object] = {"line": str(line_id)}
    if data:
        summary |= {"kind": data.kind, "value": data.value, "reason": data.reason}
    await _audit(db, order, p.user_id, "discount", summary)


@router.put("/orders/{order_id}/discount", response_model=PosOrderOut)
async def order_discount(
    order_id: uuid.UUID, body: DiscountIn, request: Request, p: Discount, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await _set_order_discount(db, order, p, body, lang)
        return await full_out(db, order, lang)


@router.delete("/orders/{order_id}/discount", response_model=PosOrderOut)
async def remove_order_discount(
    order_id: uuid.UUID, request: Request, p: Discount, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await _set_order_discount(db, order, p, None, lang)
        return await full_out(db, order, lang)


@router.put("/orders/{order_id}/lines/{line_id}/discount", response_model=PosOrderOut)
async def line_discount(
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    body: DiscountIn,
    request: Request,
    p: Discount,
    lang: Lang = "en",
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await _set_line_discount(db, order, line_id, p, body, lang)
        return await full_out(db, order, lang)


@router.delete("/orders/{order_id}/lines/{line_id}/discount", response_model=PosOrderOut)
async def remove_line_discount(
    order_id: uuid.UUID, line_id: uuid.UUID, request: Request, p: Discount, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await _set_line_discount(db, order, line_id, p, None, lang)
        return await full_out(db, order, lang)


@router.post("/orders/{order_id}/lines/{line_id}/void", response_model=PosOrderOut)
async def void_line(
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    body: VoidIn,
    request: Request,
    p: Void,
    lang: Lang = "en",
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await voids.void_line(db, order, line_id, user_id=p.user_id, reason=body.reason)
        return await full_out(db, order, lang)


@router.post("/orders/{order_id}/void", response_model=PosOrderOut)
async def void_order(
    order_id: uuid.UUID, body: VoidIn, request: Request, p: Void, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await voids.void_order(db, order, user_id=p.user_id, reason=body.reason)
        return await full_out(db, order, lang)


@router.post("/orders/{order_id}/refund", response_model=PosOrderOut)
async def refund_order(
    order_id: uuid.UUID, body: RefundIn, request: Request, p: Refund, key: Key, lang: Lang = "en"
) -> Any:
    async def work(db: AsyncSession) -> PosOrderOut:
        order = await _scoped(db, p, order_id)
        await refunds.request_refund(db, order, p, body)
        return await full_out(db, order, lang)

    return await _keyed(request, p, key, 200, work)


@router.get("/refunds", response_model=list[RefundOut])
async def list_refunds(
    outlet_id: uuid.UUID,
    request: Request,
    p: Refund,
    status: Literal["requested", "done", "rejected"] = "requested",
) -> list[RefundOut]:
    """Refunds waiting for a decision (or decided ones) at an outlet."""
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(SalesRefund)
            .where(SalesRefund.outlet_id == outlet_id, SalesRefund.status == status)
            .order_by(SalesRefund.created_at.desc())
            .limit(100)
        )
        return [refunds.refund_out(r) for r in await db.scalars(stmt)]


@router.post("/refunds/{refund_id}/{decision}", response_model=RefundOut)
async def decide_refund(
    refund_id: uuid.UUID,
    decision: Literal["approve", "reject"],
    request: Request,
    p: Refund,
) -> RefundOut:
    async with _db(request, p) as db:
        refund = await refunds.get_refund(db, refund_id)
        p.require_outlet(refund.outlet_id)
        await refunds.decide(db, refund, p, approve=decision == "approve")
        return refunds.refund_out(refund)
