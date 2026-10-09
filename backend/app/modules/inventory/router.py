"""Inventory endpoints (FR-INV-001, 003 to 005, 014, FR-X-005). Every route checks the
caller's outlet scope (docs/03): a storekeeper of one outlet never sees another's stock.
Costs and values also need catalog.cost.view (docs/03 rule 5)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.errors import ForbiddenError
from app.core.idempotency import idempotency_key, remember, replay_or_none, request_fingerprint
from app.core.pagination import Page, PageParams, page_params
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import COST_VIEW, tenant_today
from app.modules.inventory import opening, queries, trace
from app.modules.inventory import permissions as perm
from app.modules.inventory.schemas import (
    BatchOut,
    MovementOut,
    OpeningIn,
    PostedDocument,
    StockRow,
    ValuationRow,
)

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Post = Annotated[Principal, Depends(require(perm.OPENING_POST))]
Params = Annotated[PageParams, Depends(page_params)]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _viewer(p: Principal, lang: str) -> queries.Viewer:
    return queries.Viewer(tenant_id=p.tenant_id, language=lang, show_cost=p.can(COST_VIEW))


@router.get("/stock", response_model=Page[StockRow])
async def stock(
    outlet_id: uuid.UUID, request: Request, p: View, params: Params, lang: Lang = "en"
) -> Page[StockRow]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows, cursor = await queries.on_hand(db, outlet_id, params, _viewer(p, lang))
    return Page(items=rows, next_cursor=cursor)


@router.get("/stock/{item_id}/batches", response_model=list[BatchOut])
async def item_batches(
    item_id: uuid.UUID, outlet_id: uuid.UUID, request: Request, p: View
) -> list[BatchOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await queries.batches(db, outlet_id, item_id)


@router.get("/movements", response_model=Page[MovementOut])
async def movement_history(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    params: Params,
    item_id: uuid.UUID | None = None,
) -> Page[MovementOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows, cursor = await queries.movements(
            db, outlet_id, item_id, params, show_cost=p.can(COST_VIEW)
        )
    return Page(items=rows, next_cursor=cursor)


@router.get("/valuation", response_model=Page[ValuationRow])
async def stock_valuation(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    params: Params,
    on: date | None = None,
    lang: Lang = "en",
) -> Page[ValuationRow]:
    p.require_outlet(outlet_id)
    if not p.can(COST_VIEW):
        raise ForbiddenError("permission_denied")  # the report is all about value
    async with _db(request, p) as db:
        day = on or await tenant_today(db, p.tenant_id)
        rows, cursor = await queries.valuation(db, outlet_id, day, params, _viewer(p, lang))
    return Page(items=rows, next_cursor=cursor)


@router.post("/opening", response_model=PostedDocument, status_code=201)
async def post_opening(
    body: OpeningIn,
    request: Request,
    p: Post,
    key: Annotated[uuid.UUID | None, Depends(idempotency_key)],
) -> PostedDocument | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request) if key else ""
    async with _db(request, p) as db:
        if key and (stored := await replay_or_none(db, key, fingerprint)):
            return JSONResponse(stored.body, status_code=stored.status)
        out = await opening.post_opening(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        if key:
            await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
    return out


@router.post("/opening/{doc_id}/reverse", response_model=PostedDocument)
async def reverse_opening(doc_id: uuid.UUID, request: Request, p: Post) -> PostedDocument:
    async with _db(request, p) as db:
        p.require_outlet(await opening.document_outlet(db, doc_id))
        return await opening.reverse_opening(
            db, tenant_id=p.tenant_id, user_id=p.user_id, doc_id=doc_id
        )


@router.get("/lots", response_model=list[trace.TraceBatch])
async def find_lots(
    lot: Annotated[str, Query(min_length=1, max_length=64)],
    request: Request,
    p: View,
    lang: Lang = "en",
) -> list[trace.TraceBatch]:
    """FR-INV-016: batches by lot code (prefix), at outlets the caller may see."""
    async with _db(request, p) as db:
        return await trace.find_lots(db, p.tenant_id, lot.strip(), lang, p.can_access_outlet)


@router.get("/batches/{batch_id}/trace", response_model=trace.Trace)
async def trace_batch(
    batch_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> trace.Trace:
    """FR-INV-016: where a batch came from and where it went."""
    async with _db(request, p) as db:
        return await trace.trace(db, p.tenant_id, batch_id, lang, p.can_access_outlet)
