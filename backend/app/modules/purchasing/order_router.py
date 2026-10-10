"""Purchase order endpoints (FR-PUR-003, 005, 010). Outlet scope is checked on every call."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.purchasing import pdf, service
from app.modules.purchasing import permissions as perm
from app.modules.purchasing.models import PurchaseOrder
from app.modules.purchasing.schemas import DecisionIn, OrderIn, OrderOut, ReceiptOut, ReceiveIn

router = APIRouter(prefix="/api/v1/purchasing/orders", tags=["purchasing"])

View = Annotated[Principal, Depends(require(perm.VENDOR_VIEW))]
Create = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]
Approve = Annotated[Principal, Depends(require(perm.ORDER_APPROVE))]
Receive = Annotated[Principal, Depends(require(perm.RECEIPT_CREATE))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _scoped(db, p: Principal, po_id: uuid.UUID, *, lock: bool = False) -> PurchaseOrder:  # type: ignore[no-untyped-def]
    po = await service.get_order(db, po_id, lock=lock)
    p.require_outlet(po.outlet_id)  # out of scope looks like "not found"
    return po


@router.get("", response_model=list[OrderOut])
async def list_orders(outlet_id: uuid.UUID, request: Request, p: View) -> list[OrderOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.outlet_id == outlet_id)
            .order_by(PurchaseOrder.created_at.desc())
            .limit(100)
        )
        return [await service.order_out(db, po) for po in await db.scalars(stmt)]


@router.get("/{po_id}", response_model=OrderOut)
async def get_order(po_id: uuid.UUID, request: Request, p: View) -> OrderOut:
    async with _db(request, p) as db:
        return await service.order_out(db, await _scoped(db, p, po_id))


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(body: OrderIn, request: Request, p: Create) -> OrderOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        po = await service.save_order(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await service.order_out(db, po)


@router.put("/{po_id}", response_model=OrderOut)
async def update_order(po_id: uuid.UUID, body: OrderIn, request: Request, p: Create) -> OrderOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        await _scoped(db, p, po_id)
        po = await service.save_order(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, po_id=po_id
        )
        return await service.order_out(db, po)


@router.post("/{po_id}/submit", response_model=OrderOut)
async def submit_order(po_id: uuid.UUID, request: Request, p: Create) -> OrderOut:
    async with _db(request, p) as db:
        await _scoped(db, p, po_id)
        return await service.order_out(db, await service.submit(db, user_id=p.user_id, po_id=po_id))


@router.post("/{po_id}/decide", response_model=OrderOut)
async def decide_order(
    po_id: uuid.UUID, body: DecisionIn, request: Request, p: Approve
) -> OrderOut:
    async with _db(request, p) as db:
        await _scoped(db, p, po_id)
        po = await service.decide(
            db, user_id=p.user_id, role_id=p.role_id, po_id=po_id, approve=body.approve
        )
        return await service.order_out(db, po)


@router.post("/{po_id}/cancel", response_model=OrderOut)
async def cancel_order(po_id: uuid.UUID, request: Request, p: Create) -> OrderOut:
    async with _db(request, p) as db:
        await _scoped(db, p, po_id)
        return await service.order_out(db, await service.cancel(db, user_id=p.user_id, po_id=po_id))


@router.post("/{po_id}/receipts", response_model=ReceiptOut, status_code=201)
async def receive_order(
    po_id: uuid.UUID,
    body: ReceiveIn,
    request: Request,
    p: Receive,
    key: Annotated[uuid.UUID, Depends(required_idempotency_key)],
) -> ReceiptOut | JSONResponse:
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        await _scoped(db, p, po_id)
        receipt = await service.receive(
            db, tenant_id=p.tenant_id, user_id=p.user_id, po_id=po_id, data=body
        )
        out = await service.receipt_out(db, receipt)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.get("/{po_id}/pdf")
async def order_pdf(po_id: uuid.UUID, request: Request, p: View, lang: str = "en") -> Response:
    async with _db(request, p) as db:
        po = await _scoped(db, p, po_id)
        data = await pdf.order_pdf_data(db, po, lang[:5])
    name = (po.number or "draft").replace('"', "")
    return Response(
        await pdf.render(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
