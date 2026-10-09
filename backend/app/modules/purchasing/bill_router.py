"""Vendor bills, three-way match, payments and payables (FR-PUR-009). Outlet scope on every
call; the payables list covers only outlets the caller may see."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import tenant_today
from app.modules.purchasing import bills
from app.modules.purchasing import permissions as perm
from app.modules.purchasing.ap_models import VendorBill
from app.modules.purchasing.ap_schemas import (
    ApplyCreditIn,
    PayableRow,
    PaymentIn,
    VendorBillIn,
    VendorBillOut,
)

router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

View = Annotated[Principal, Depends(require(perm.BILL_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.BILL_MANAGE))]
Pay = Annotated[Principal, Depends(require(perm.BILL_PAY))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Status = Literal["open", "partially_paid", "paid", "void"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _bill(db, p: Principal, bill_id: uuid.UUID) -> VendorBill:  # type: ignore[no-untyped-def]
    bill = await bills.get_bill(db, bill_id, lock=True)
    p.require_outlet(bill.outlet_id)
    return bill


@router.get("/bills", response_model=list[VendorBillOut])
async def list_bills(
    outlet_id: uuid.UUID, request: Request, p: View, status: Status | None = None
) -> list[VendorBillOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return [await bills.bill_out(db, b) for b in await bills.list_bills(db, outlet_id, status)]


@router.get("/bills/{bill_id}", response_model=VendorBillOut)
async def get_bill(bill_id: uuid.UUID, request: Request, p: View) -> VendorBillOut:
    async with _db(request, p) as db:
        bill = await bills.get_bill(db, bill_id)
        p.require_outlet(bill.outlet_id)
        return await bills.bill_out(db, bill)


@router.post("/bills", response_model=VendorBillOut, status_code=201)
async def create_bill(
    body: VendorBillIn, request: Request, p: Manage, key: Key
) -> VendorBillOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        bill = await bills.create_bill(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await bills.bill_out(db, bill)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/bills/{bill_id}/payments", response_model=VendorBillOut, status_code=201)
async def pay_bill(
    bill_id: uuid.UUID, body: PaymentIn, request: Request, p: Pay, key: Key
) -> VendorBillOut | JSONResponse:
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        bill = await _bill(db, p, bill_id)
        await bills.pay(db, bill, user_id=p.user_id, data=body)
        out = await bills.bill_out(db, bill)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/bills/{bill_id}/payments/{payment_id}/reverse", response_model=VendorBillOut)
async def reverse_payment(
    bill_id: uuid.UUID, payment_id: uuid.UUID, request: Request, p: Pay
) -> VendorBillOut:
    async with _db(request, p) as db:
        bill = await _bill(db, p, bill_id)
        today = await tenant_today(db, p.tenant_id)
        await bills.reverse_payment(db, bill, payment_id, user_id=p.user_id, on=today)
        return await bills.bill_out(db, bill)


@router.post("/bills/{bill_id}/credits", response_model=VendorBillOut)
async def apply_credit(
    bill_id: uuid.UUID, body: ApplyCreditIn, request: Request, p: Manage
) -> VendorBillOut:
    async with _db(request, p) as db:
        bill = await _bill(db, p, bill_id)
        await bills.apply_credit(db, bill, body.return_id, user_id=p.user_id)
        return await bills.bill_out(db, bill)


@router.post("/bills/{bill_id}/void", response_model=VendorBillOut)
async def void_bill(bill_id: uuid.UUID, request: Request, p: Manage) -> VendorBillOut:
    async with _db(request, p) as db:
        bill = await _bill(db, p, bill_id)
        await bills.void_bill(db, bill, user_id=p.user_id)
        return await bills.bill_out(db, bill)


@router.get("/payables", response_model=list[PayableRow])
async def payables(request: Request, p: View) -> list[PayableRow]:
    async with _db(request, p) as db:
        today = await tenant_today(db, p.tenant_id)
        scope = None if p.all_outlets else set(p.outlet_ids)
        return await bills.payables(db, scope, today)
