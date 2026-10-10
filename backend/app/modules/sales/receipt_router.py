"""Receipt endpoints (FR-SAL-010): JSON for Bluetooth printing in the browser, and PDF."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.access.policy import Principal, require
from app.modules.sales import permissions as perm
from app.modules.sales.pos_router import _db, _scoped
from app.modules.sales.receipt_pdf import receipt_pdf
from app.modules.sales.receipts import SaleReceiptOut, receipt

router = APIRouter(prefix="/api/v1/pos/orders", tags=["pos"])
Take = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]
Lang = Literal["en", "id"]


@router.get("/{order_id}/receipt", response_model=SaleReceiptOut)
async def get_receipt(
    order_id: uuid.UUID, request: Request, p: Take, lang: Lang = "id"
) -> SaleReceiptOut:
    async with _db(request, p) as db:
        return await receipt(db, await _scoped(db, p, order_id, lock=False), lang)


@router.get("/{order_id}/receipt/pdf")
async def get_receipt_pdf(
    order_id: uuid.UUID, request: Request, p: Take, lang: Lang = "id"
) -> Response:
    async with _db(request, p) as db:
        r = await receipt(db, await _scoped(db, p, order_id, lock=False), lang)
    return Response(
        await receipt_pdf(r, lang),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{r.number}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
