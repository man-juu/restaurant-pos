"""Purchasing endpoints, part 1 (FR-PUR-001, 002, 004 to 006, 011)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.tenancy import tenant_session
from app.core.uploads import service as uploads
from app.modules.purchasing import permissions as perm
from app.modules.purchasing import service, vendors
from app.modules.purchasing.schemas import (
    QuickPurchaseIn,
    ReceiptOut,
    VendorIn,
    VendorItemIn,
    VendorItemOut,
    VendorOut,
)

router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

View = Annotated[Principal, Depends(require(perm.VENDOR_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.VENDOR_MANAGE))]
Receive = Annotated[Principal, Depends(require(perm.RECEIPT_CREATE))]
Reverse = Annotated[Principal, Depends(require(perm.RECEIPT_REVERSE))]


class BankDetails(BaseModel):
    bank_details: str | None


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/vendors", response_model=list[VendorOut])
async def list_vendors(
    request: Request, p: View, include_inactive: bool = False
) -> list[VendorOut]:
    async with _db(request, p) as db:
        return [vendors.out(v) for v in await service.list_vendors(db, include_inactive)]


@router.post("/vendors", response_model=VendorOut, status_code=201)
async def create_vendor(body: VendorIn, request: Request, p: Manage) -> VendorOut:
    async with _db(request, p) as db:
        v = await service.save_vendor(
            db, request.app.state.secret_box, tenant_id=p.tenant_id, user_id=p.user_id, data=body
        )
        return vendors.out(v)


@router.put("/vendors/{vendor_id}", response_model=VendorOut)
async def update_vendor(
    vendor_id: uuid.UUID, body: VendorIn, request: Request, p: Manage
) -> VendorOut:
    async with _db(request, p) as db:
        v = await service.save_vendor(
            db,
            request.app.state.secret_box,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            data=body,
            vendor_id=vendor_id,
        )
        return vendors.out(v)


@router.post("/vendors/{vendor_id}/bank-details", response_model=BankDetails)
async def reveal_bank_details(vendor_id: uuid.UUID, request: Request, p: Manage) -> BankDetails:
    """POST, not GET: viewing is an audited action and is never cached or prefetched."""
    async with _db(request, p) as db:
        value = await service.reveal_bank_details(
            db,
            request.app.state.secret_box,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            vendor_id=vendor_id,
        )
    return BankDetails(bank_details=value)


@router.get("/vendors/{vendor_id}/items", response_model=list[VendorItemOut])
async def vendor_items(vendor_id: uuid.UUID, request: Request, p: View) -> list[VendorItemOut]:
    async with _db(request, p) as db:
        rows = await service.list_vendor_items(db, vendor_id)
        return [VendorItemOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/vendors/{vendor_id}/items", response_model=VendorItemOut, status_code=201)
async def add_vendor_item(
    vendor_id: uuid.UUID, body: VendorItemIn, request: Request, p: Manage
) -> VendorItemOut:
    async with _db(request, p) as db:
        row = await service.add_vendor_item(
            db, tenant_id=p.tenant_id, user_id=p.user_id, vendor_id=vendor_id, data=body
        )
        return VendorItemOut.model_validate(row, from_attributes=True)


@router.put("/attachments", response_model=uploads.UploadRef, status_code=201)
async def upload_invoice(request: Request, p: Receive) -> uploads.UploadRef:
    """FR-PUR-011: photo of a supplier invoice or delivery note (JPEG, PNG or WebP)."""
    settings = request.app.state.settings
    raw = await uploads.read_body(request, settings.upload_max_bytes)
    async with _db(request, p) as db:
        row = await uploads.store_image(
            db, settings, tenant_id=p.tenant_id, user_id=p.user_id, purpose="invoice", raw=raw
        )
        return uploads.UploadRef.model_validate(row, from_attributes=True)


@router.get("/receipts", response_model=list[ReceiptOut])
async def list_receipts(outlet_id: uuid.UUID, request: Request, p: View) -> list[ReceiptOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return [
            await service.receipt_out(db, r) for r in await service.list_receipts(db, outlet_id)
        ]


@router.post("/quick-purchases", response_model=ReceiptOut, status_code=201)
async def quick_purchase(
    body: QuickPurchaseIn,
    request: Request,
    p: Receive,
    key: Annotated[uuid.UUID, Depends(required_idempotency_key)],
) -> ReceiptOut | JSONResponse:
    """A retried request (bad connection at the market) never receives the stock twice."""
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        receipt = await service.quick_purchase(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body
        )
        out = await service.receipt_out(db, receipt)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/receipts/{receipt_id}/reverse", response_model=ReceiptOut)
async def reverse_receipt(receipt_id: uuid.UUID, request: Request, p: Reverse) -> ReceiptOut:
    async with _db(request, p) as db:
        receipt = await service.reverse_receipt(db, user_id=p.user_id, receipt_id=receipt_id)
        p.require_outlet(receipt.outlet_id)
        return await service.receipt_out(db, receipt)
