"""Returns to vendors and credit notes (FR-PUR-008). Outlet scope on every call."""

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
from app.modules.purchasing import permissions as perm
from app.modules.purchasing import returns
from app.modules.purchasing.ap_schemas import (
    BaseLine,
    CreditNoteIn,
    VendorReturnIn,
    VendorReturnOut,
)

router = APIRouter(prefix="/api/v1/purchasing/returns", tags=["purchasing"])

View = Annotated[Principal, Depends(require(perm.VENDOR_VIEW))]
Create = Annotated[Principal, Depends(require(perm.RETURN_CREATE))]
Reverse = Annotated[Principal, Depends(require(perm.RECEIPT_REVERSE))]
Credit = Annotated[Principal, Depends(require(perm.BILL_MANAGE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[VendorReturnOut])
async def list_returns(
    outlet_id: uuid.UUID, request: Request, p: View, vendor_id: uuid.UUID | None = None
) -> list[VendorReturnOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows = await returns.list_returns(db, outlet_id, vendor_id)
        return [await returns.return_out(db, r) for r in rows]


@router.get("/receipt-lines/{receipt_id}", response_model=list[BaseLine])
async def receipt_lines(
    receipt_id: uuid.UUID, request: Request, p: View, lang: Literal["en", "id"] = "en"
) -> list[BaseLine]:
    """A receipt's lines in base units: the starting point for a return or a bill."""
    async with _db(request, p) as db:
        receipt, lines = await returns.receipt_base_lines(db, p.tenant_id, receipt_id, lang)
        p.require_outlet(receipt.outlet_id)
        return lines


@router.post("", response_model=VendorReturnOut, status_code=201)
async def post_return(
    body: VendorReturnIn, request: Request, p: Create, key: Key
) -> VendorReturnOut | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        doc = await returns.post_return(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await returns.return_out(db, doc)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/{return_id}/reverse", response_model=VendorReturnOut)
async def reverse_return(return_id: uuid.UUID, request: Request, p: Reverse) -> VendorReturnOut:
    async with _db(request, p) as db:
        doc = await returns.get_return(db, return_id, lock=True)
        p.require_outlet(doc.outlet_id)
        today = await tenant_today(db, p.tenant_id)
        await returns.reverse_return(db, doc, user_id=p.user_id, on=today)
        return await returns.return_out(db, doc)


@router.post("/{return_id}/credit-note", response_model=VendorReturnOut)
async def credit_note(
    return_id: uuid.UUID, body: CreditNoteIn, request: Request, p: Credit
) -> VendorReturnOut:
    async with _db(request, p) as db:
        doc = await returns.get_return(db, return_id, lock=True)
        p.require_outlet(doc.outlet_id)
        await returns.record_credit_note(db, doc, user_id=p.user_id, data=body)
        return await returns.return_out(db, doc)
