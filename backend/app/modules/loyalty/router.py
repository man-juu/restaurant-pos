"""Loyalty endpoints (FR-SAL-016). Points and vouchers are tenant-wide (a guest earns at one
outlet and spends at another); earning checks the receipt's outlet against the caller."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
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
from app.modules.loyalty import permissions as perm
from app.modules.loyalty import service
from app.modules.loyalty.models import LoyaltyEntry, Voucher
from app.modules.loyalty.schemas import (
    BalanceOut,
    EarnIn,
    EarnOut,
    EntryOut,
    RedeemIn,
    VoucherIn,
    VoucherOut,
)

router = APIRouter(prefix="/api/v1/loyalty", tags=["loyalty"])
View = Annotated[Principal, Depends(require(perm.POINTS_VIEW))]
Earn = Annotated[Principal, Depends(require(perm.POINTS_EARN))]
Redeem = Annotated[Principal, Depends(require(perm.POINTS_REDEEM))]
Manage = Annotated[Principal, Depends(require(perm.VOUCHER_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _voucher(v: Voucher) -> VoucherOut:
    return VoucherOut.model_validate(v, from_attributes=True)


@router.get("/customers/{customer_id}", response_model=BalanceOut)
async def customer_points(customer_id: uuid.UUID, request: Request, p: View) -> BalanceOut:
    async with _db(request, p) as db:
        await service.guest(db, customer_id)
        c = await service.conf(db, p.tenant_id)
        entries = await db.scalars(
            select(LoyaltyEntry)
            .where(LoyaltyEntry.customer_id == customer_id)
            .order_by(LoyaltyEntry.created_at.desc())
            .limit(50)
        )
        vouchers = await db.scalars(
            select(Voucher)
            .where(Voucher.customer_id == customer_id, Voucher.status == "active")
            .order_by(Voucher.created_at.desc())
        )
        return BalanceOut(
            customer_id=customer_id,
            balance=await service.balance(db, customer_id),
            point_value=c.point_value,
            min_redeem_points=c.min_redeem_points,
            entries=[EntryOut.model_validate(e, from_attributes=True) for e in entries],
            vouchers=[_voucher(v) for v in vouchers],
        )


@router.post("/earn", response_model=EarnOut)
async def earn(body: EarnIn, request: Request, p: Earn) -> EarnOut:
    """Idempotent by receipt: asking twice gives the points once."""
    async with _db(request, p) as db:
        points = await service.earn(db, p, body.document_id, body.customer_id)
        return EarnOut(points=points, balance=await service.balance(db, body.customer_id))


@router.post("/redeem", response_model=VoucherOut, status_code=201)
async def redeem(body: RedeemIn, request: Request, p: Redeem, key: Key) -> Any:
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        out = _voucher(await service.redeem(db, p.tenant_id, p.user_id, body))
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.get("/vouchers", response_model=list[VoucherOut])
async def vouchers(
    request: Request, p: Manage, status: Literal["active", "used", "void"] = "active"
) -> list[VoucherOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(
            select(Voucher)
            .where(Voucher.status == status)
            .order_by(Voucher.created_at.desc())
            .limit(200)
        )
        return [_voucher(v) for v in rows]


@router.get("/vouchers/by-code/{code}", response_model=VoucherOut)
async def voucher_by_code(code: str, request: Request, p: View) -> VoucherOut:
    async with _db(request, p) as db:
        return _voucher(await service.find_voucher(db, code))


@router.post("/vouchers", response_model=VoucherOut, status_code=201)
async def issue(body: VoucherIn, request: Request, p: Manage, key: Key) -> Any:
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        out = _voucher(await service.issue(db, p.tenant_id, p.user_id, body))
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/vouchers/{voucher_id}/void", response_model=VoucherOut)
async def void(voucher_id: uuid.UUID, request: Request, p: Manage) -> VoucherOut:
    async with _db(request, p) as db:
        return _voucher(await service.void(db, voucher_id, p.user_id))
