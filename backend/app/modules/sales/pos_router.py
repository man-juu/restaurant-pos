"""POS order endpoints (FR-SAL-004 to 006). Outlet scope on every call: an order in another
outlet looks like one that does not exist. Creating, adding lines and paying take an
idempotency key, because a till on shaky Wi-Fi retries."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.sales import orders, payments
from app.modules.sales import permissions as perm
from app.modules.sales.models import (
    Payment,
    PosLineModifier,
    PosOrder,
    PosOrderLine,
    SalesDocument,
    SalesRefund,
)
from app.modules.sales.pos_schemas import (
    PosLineIn,
    PosLineUpdateIn,
    PosOrderCreateIn,
    PosOrderOut,
    PosOrderSummary,
    PosPayIn,
    PosPaymentOut,
)
from app.modules.sales.refunds import refund_out

router = APIRouter(prefix="/api/v1/pos/orders", tags=["pos"])

Take = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]
Pay = Annotated[Principal, Depends(require(perm.ORDER_PAY))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Lang = Literal["en", "id"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _scoped(
    db: AsyncSession, p: Principal, order_id: uuid.UUID, *, lock: bool = True
) -> PosOrder:
    order = await orders.get_order(db, order_id, lock=lock)
    p.require_outlet(order.outlet_id)
    return order


async def full_out(db: AsyncSession, order: PosOrder, lang: str) -> PosOrderOut:
    out = await orders.order_out(db, order, lang)
    if order.document_id is None:
        return out
    latest = await db.scalar(
        select(SalesRefund)
        .where(SalesRefund.order_id == order.id)
        .order_by(SalesRefund.created_at.desc())
        .limit(1)
    )
    out.refund = refund_out(latest) if latest else None
    doc = await db.get(SalesDocument, order.document_id)
    rows = await db.scalars(
        select(Payment).where(Payment.document_id == order.document_id).order_by(Payment.paid_at)
    )
    out.payments = [
        PosPaymentOut(
            method=r.method_code,
            kind=r.kind,
            amount=r.amount,
            tendered=r.tendered,
            change=r.change,
            reference=r.reference,
        )
        for r in rows
    ]
    if doc is not None:
        out.tip, out.rounding = doc.tip, doc.rounding
    return out


async def _keyed(
    request: Request,
    p: Principal,
    key: uuid.UUID,
    status: int,
    work: Callable[[AsyncSession], Awaitable[PosOrderOut]],
) -> PosOrderOut | JSONResponse:
    """Run `work` once per idempotency key; a retry gets the stored answer."""
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        out = await work(db)
        await remember(db, p.tenant_id, key, fingerprint, status, out.model_dump(mode="json"))
        return out


@router.get("", response_model=list[PosOrderSummary])
async def list_orders(
    outlet_id: uuid.UUID,
    request: Request,
    p: Take,
    status: Literal["open", "paid", "cancelled", "void", "refunded"] = "open",
) -> list[PosOrderSummary]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(PosOrder)
            .where(PosOrder.outlet_id == outlet_id, PosOrder.status == status)
            .order_by(PosOrder.created_at.desc())
            .limit(200)
        )
        found = list(await db.scalars(stmt))
        subtotals, counts = await _subtotals(db, [o.id for o in found])
        return [
            PosOrderSummary(
                id=o.id,
                number=o.number,
                status=o.status,
                label=o.label,
                channel_id=o.channel_id,
                created_at=o.created_at,
                total=subtotals.get(o.id, 0),
                lines=counts.get(o.id, 0),
            )
            for o in found
        ]


async def _subtotals(
    db: AsyncSession, ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Line totals per order (before service charge and tax), in two queries."""
    lines = list(await db.scalars(select(PosOrderLine).where(PosOrderLine.order_id.in_(ids))))
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
    return totals, counts


@router.post("", response_model=PosOrderOut, status_code=201)
async def create_order(
    body: PosOrderCreateIn, request: Request, p: Take, key: Key, lang: Lang = "en"
) -> Any:
    p.require_outlet(body.outlet_id)

    async def work(db: AsyncSession) -> PosOrderOut:
        order = await orders.create_order(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await full_out(db, order, lang)

    return await _keyed(request, p, key, 201, work)


@router.get("/{order_id}", response_model=PosOrderOut)
async def get_order(
    order_id: uuid.UUID, request: Request, p: Take, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        return await full_out(db, await _scoped(db, p, order_id, lock=False), lang)


@router.post("/{order_id}/lines", response_model=PosOrderOut)
async def add_line(
    order_id: uuid.UUID, body: PosLineIn, request: Request, p: Take, key: Key, lang: Lang = "en"
) -> Any:
    async def work(db: AsyncSession) -> PosOrderOut:
        order = await _scoped(db, p, order_id)
        await orders.add_line(db, order, user_id=p.user_id, data=body)
        return await full_out(db, order, lang)

    return await _keyed(request, p, key, 200, work)


@router.put("/{order_id}/lines/{line_id}", response_model=PosOrderOut)
async def update_line(
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    body: PosLineUpdateIn,
    request: Request,
    p: Take,
    lang: Lang = "en",
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await orders.update_line(db, order, line_id, body)
        return await full_out(db, order, lang)


@router.delete("/{order_id}/lines/{line_id}", response_model=PosOrderOut)
async def remove_line(
    order_id: uuid.UUID, line_id: uuid.UUID, request: Request, p: Take, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await orders.remove_line(db, order, line_id)
        return await full_out(db, order, lang)


@router.post("/{order_id}/send", response_model=PosOrderOut)
async def send_order(
    order_id: uuid.UUID, request: Request, p: Take, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await orders.send(db, order, p.user_id)
        return await full_out(db, order, lang)


@router.post("/{order_id}/cancel", response_model=PosOrderOut)
async def cancel_order(
    order_id: uuid.UUID, request: Request, p: Take, lang: Lang = "en"
) -> PosOrderOut:
    async with _db(request, p) as db:
        order = await _scoped(db, p, order_id)
        await orders.cancel(db, order, p.user_id)
        return await full_out(db, order, lang)


@router.post("/{order_id}/pay", response_model=PosOrderOut)
async def pay_order(
    order_id: uuid.UUID, body: PosPayIn, request: Request, p: Pay, key: Key, lang: Lang = "en"
) -> Any:
    async def work(db: AsyncSession) -> PosOrderOut:
        order = await _scoped(db, p, order_id)
        await payments.pay(db, order, user_id=p.user_id, data=body, language=lang)
        return await full_out(db, order, lang)

    return await _keyed(request, p, key, 200, work)
