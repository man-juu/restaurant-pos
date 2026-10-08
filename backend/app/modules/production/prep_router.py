"""Prep list (FR-PRD-008) and shelf-life labels (FR-PRD-007). Outlet scope on every call."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.errors import ConflictError
from app.core.models import Tenant
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import item_names, stock_items
from app.modules.production import pdf, prep, service
from app.modules.production import permissions as perm
from app.modules.production.schemas import PrepRow

router = APIRouter(prefix="/api/v1/production", tags=["production"])

View = Annotated[Principal, Depends(require(perm.ORDER_VIEW))]
Lang = Literal["en", "id"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _pdf(body: bytes, name: str) -> Response:
    return Response(
        body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{name}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/prep-list", response_model=list[PrepRow])
async def prep_list(
    outlet_id: uuid.UUID, on: date, request: Request, p: View, lang: Lang = "en"
) -> list[PrepRow]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await prep.prep_list(db, p.tenant_id, outlet_id, on, lang)


@router.get("/prep-list/pdf")
async def prep_list_pdf(
    outlet_id: uuid.UUID, on: date, request: Request, p: View, lang: Lang = "en"
) -> Response:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows = await prep.prep_list(db, p.tenant_id, outlet_id, on, lang)
    title = f"{pdf.words(lang)['prep']} {on.strftime('%d/%m/%Y')}"
    return _pdf(await pdf.prep(title, rows, lang), f"prep-{on.isoformat()}")


@router.get("/orders/{order_id}/labels")
async def labels(
    order_id: uuid.UUID,
    request: Request,
    p: View,
    copies: Annotated[int, Query(ge=1, le=pdf.MAX_COPIES)] = 1,
    lang: Lang = "en",
) -> Response:
    async with _db(request, p) as db:
        order = await service.get_order(db, order_id)
        p.require_outlet(order.outlet_id)
        if order.status != "completed":
            raise ConflictError("wrong_status", details={"status": order.status})
        item = (await stock_items(db, {order.item_id}))[order.item_id]
        name = (await item_names(db, p.tenant_id, lang, {order.item_id}))[order.item_id].name
        tz = await db.scalar(select(Tenant.timezone).where(Tenant.id == p.tenant_id))
    label = pdf.Label(
        name=name,
        lot=order.lot_code or order.number,
        made_at=order.completed_at,
        use_by=order.expiry_date,
        storage=item.storage_type,
        allergens=item.allergens,
        timezone=tz or "UTC",
        language=lang,
    )
    return _pdf(await pdf.labels(label, copies), f"labels-{order.number}")
