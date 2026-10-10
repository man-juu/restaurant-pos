"""Wholesale invoices, customer payments and receivables aging (FR-SAL-011, FR-FIN-006)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.aging import AgingRow
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import tenant_today
from app.modules.sales import permissions as perm
from app.modules.sales import wholesale
from app.modules.sales.wholesale_models import Receivable
from app.modules.sales.wholesale_schemas import InvoiceIn, InvoiceOut, ReceiptIn

router = APIRouter(prefix="/api/v1/sales/invoices", tags=["sales"])

View = Annotated[Principal, Depends(require(perm.INVOICE_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.INVOICE_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Status = Literal["open", "partially_paid", "paid", "void"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _scoped(db, p: Principal, invoice_id: uuid.UUID) -> Receivable:  # type: ignore[no-untyped-def]
    row = await wholesale.get(db, invoice_id, lock=True)
    p.require_outlet(row.outlet_id)
    return row


async def _one(db, row: Receivable) -> InvoiceOut:  # type: ignore[no-untyped-def]
    [found] = await wholesale.out(db, [row])
    return found


@router.get("", response_model=list[InvoiceOut])
async def list_invoices(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    status: Status | None = None,
    customer_id: uuid.UUID | None = None,
) -> list[InvoiceOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = select(Receivable).where(Receivable.outlet_id == outlet_id)
        if status:
            stmt = stmt.where(Receivable.status == status)
        if customer_id:
            stmt = stmt.where(Receivable.customer_id == customer_id)
        rows = list(await db.scalars(stmt.order_by(Receivable.invoice_date.desc()).limit(200)))
        return await wholesale.out(db, rows)


@router.post("", response_model=InvoiceOut, status_code=201)
async def create(
    body: InvoiceIn, request: Request, p: Manage, key: Key
) -> InvoiceOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        row = await wholesale.create_invoice(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body
        )
        result = await _one(db, row)
        await remember(db, p.tenant_id, key, fingerprint, 201, result.model_dump(mode="json"))
        return result


@router.get("/aging", response_model=list[AgingRow])
async def aging(
    request: Request, p: View, as_of: Annotated[date | None, Query()] = None
) -> list[AgingRow]:
    async with _db(request, p) as db:
        today = as_of or await tenant_today(db, p.tenant_id)
        return await wholesale.aging(db, today, None if p.all_outlets else set(p.outlet_ids))


@router.post("/{invoice_id}/payments", response_model=InvoiceOut, status_code=201)
async def receive(
    invoice_id: uuid.UUID, body: ReceiptIn, request: Request, p: Manage, key: Key
) -> InvoiceOut | JSONResponse:
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        row = await _scoped(db, p, invoice_id)
        await wholesale.receive(db, row, user_id=p.user_id, data=body)
        result = await _one(db, row)
        await remember(db, p.tenant_id, key, fingerprint, 201, result.model_dump(mode="json"))
        return result


@router.post("/{invoice_id}/payments/{payment_id}/reverse", response_model=InvoiceOut)
async def reverse_payment(
    invoice_id: uuid.UUID, payment_id: uuid.UUID, request: Request, p: Manage
) -> InvoiceOut:
    async with _db(request, p) as db:
        row = await _scoped(db, p, invoice_id)
        today = await tenant_today(db, p.tenant_id)
        await wholesale.reverse_payment(db, row, payment_id, user_id=p.user_id, on=today)
        return await _one(db, row)


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
async def void(invoice_id: uuid.UUID, request: Request, p: Manage) -> InvoiceOut:
    async with _db(request, p) as db:
        row = await _scoped(db, p, invoice_id)
        await wholesale.void(db, row, user_id=p.user_id)
        return await _one(db, row)
