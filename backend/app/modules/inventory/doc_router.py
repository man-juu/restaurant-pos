"""Waste, adjustment and count endpoints (FR-INV-007 to 009). Every route checks the
caller's outlet scope (docs/03); approvals also check the rule's role and that nobody
approves their own document (docs/03 rule 1)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.idempotency import idempotency_key, remember, replay_or_none, request_fingerprint
from app.core.tenancy import tenant_session
from app.modules.inventory import counts, doc_queries, documents, estimates
from app.modules.inventory import permissions as perm
from app.modules.inventory.doc_queries import HEADERS, Kind
from app.modules.inventory.doc_schemas import (
    AdjustmentIn,
    CountedIn,
    CountIn,
    StockDocument,
    WasteIn,
)
from app.modules.inventory.estimates import SetOnHandIn

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Waste = Annotated[Principal, Depends(require(perm.WASTE_CREATE))]
AdjCreate = Annotated[Principal, Depends(require(perm.ADJUSTMENT_CREATE))]
AdjApprove = Annotated[Principal, Depends(require(perm.ADJUSTMENT_APPROVE))]
CountCreate = Annotated[Principal, Depends(require(perm.COUNT_CREATE))]
CountApprove = Annotated[Principal, Depends(require(perm.COUNT_APPROVE))]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]
Decision = Literal["approve", "reject"]
KindPath = Literal["waste", "adjustments", "counts"]
KIND_PATHS: dict[str, Kind] = {"waste": "waste", "adjustments": "adjustment", "counts": "count"}


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _read(request: Request, p: Principal, kind: Kind, doc_id: uuid.UUID) -> StockDocument:
    async with _db(request, p) as db:
        doc = await doc_queries.get_document(
            db,
            tenant_id=p.tenant_id,
            kind=kind,
            doc_id=doc_id,
            language="en",
            show_system=p.can(perm.COUNT_APPROVE),
        )
    p.require_outlet(doc.outlet_id)
    return doc


async def _scoped(request: Request, p: Principal, kind: Kind, doc_id: uuid.UUID) -> None:
    """404 for documents of outlets outside the caller's scope (docs/03)."""
    async with _db(request, p) as db:
        doc = await db.get(HEADERS[kind], doc_id)
    if doc is not None:
        p.require_outlet(doc.outlet_id)


# ─── Reading ──────────────────────────────────────────────────────────────


@router.get("/documents/{kind}", response_model=list[StockDocument])
async def list_documents(
    kind: KindPath, outlet_id: uuid.UUID, request: Request, p: View
) -> list[StockDocument]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await doc_queries.list_documents(db, KIND_PATHS[kind], outlet_id)


@router.get("/documents/{kind}/{doc_id}", response_model=StockDocument)
async def get_document(
    kind: KindPath, doc_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> StockDocument:
    async with _db(request, p) as db:
        doc = await doc_queries.get_document(
            db,
            tenant_id=p.tenant_id,
            kind=KIND_PATHS[kind],
            doc_id=doc_id,
            language=lang,
            show_system=p.can(perm.COUNT_APPROVE),
        )
    p.require_outlet(doc.outlet_id)
    return doc


# ─── Waste (FR-INV-008) ───────────────────────────────────────────────────


@router.post("/waste", response_model=StockDocument, status_code=201)
async def post_waste(
    body: WasteIn,
    request: Request,
    p: Waste,
    key: Annotated[uuid.UUID | None, Depends(idempotency_key)],
) -> StockDocument | JSONResponse:
    p.require_outlet(body.outlet_id)
    fingerprint = await request_fingerprint(request) if key else ""
    async with _db(request, p) as db:
        if key and (stored := await replay_or_none(db, key, fingerprint)):
            return JSONResponse(stored.body, status_code=stored.status)
        log = await documents.post_waste(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await doc_queries.get_document(
            db, tenant_id=p.tenant_id, kind="waste", doc_id=log.id, language="en", show_system=True
        )
        if key:
            await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
    return out


@router.post("/waste/{doc_id}/reverse", response_model=StockDocument)
async def reverse_waste(doc_id: uuid.UUID, request: Request, p: AdjApprove) -> StockDocument:
    await _scoped(request, p, "waste", doc_id)
    async with _db(request, p) as db:
        await documents.reverse_waste(db, user_id=p.user_id, waste_id=doc_id)
    return await _read(request, p, "waste", doc_id)


# ─── Adjustments (FR-INV-009) ─────────────────────────────────────────────


@router.post("/adjustments", response_model=StockDocument, status_code=201)
async def create_adjustment(body: AdjustmentIn, request: Request, p: AdjCreate) -> StockDocument:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        adj = await documents.save_adjustment(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body
        )
    return await _read(request, p, "adjustment", adj.id)


@router.post("/stock/set-on-hand", response_model=StockDocument | None)
async def set_on_hand(body: SetOnHandIn, request: Request, p: AdjCreate) -> StockDocument | None:
    """Estimated items only: post the difference to what is on hand now."""
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        adj = await estimates.set_on_hand(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
    return await _read(request, p, "adjustment", adj.id) if adj else None


@router.put("/adjustments/{doc_id}", response_model=StockDocument)
async def update_adjustment(
    doc_id: uuid.UUID, body: AdjustmentIn, request: Request, p: AdjCreate
) -> StockDocument:
    p.require_outlet(body.outlet_id)
    await _scoped(request, p, "adjustment", doc_id)
    async with _db(request, p) as db:
        await documents.save_adjustment(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, adjustment_id=doc_id
        )
    return await _read(request, p, "adjustment", doc_id)


@router.post("/adjustments/{doc_id}/submit", response_model=StockDocument)
async def submit_adjustment(doc_id: uuid.UUID, request: Request, p: AdjCreate) -> StockDocument:
    await _scoped(request, p, "adjustment", doc_id)
    async with _db(request, p) as db:
        await documents.submit_adjustment(db, user_id=p.user_id, adjustment_id=doc_id)
    return await _read(request, p, "adjustment", doc_id)


@router.post("/adjustments/{doc_id}/{decision}", response_model=StockDocument)
async def decide_adjustment(
    doc_id: uuid.UUID, decision: Decision, request: Request, p: AdjApprove
) -> StockDocument:
    await _scoped(request, p, "adjustment", doc_id)
    async with _db(request, p) as db:
        await documents.decide_adjustment(
            db,
            user_id=p.user_id,
            role_id=p.role_id,
            adjustment_id=doc_id,
            approve=decision == "approve",
        )
    return await _read(request, p, "adjustment", doc_id)


# ─── Counts (FR-INV-007) ──────────────────────────────────────────────────


@router.post("/counts", response_model=StockDocument, status_code=201)
async def start_count(body: CountIn, request: Request, p: CountCreate) -> StockDocument:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        count = await counts.start_count(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
    return await _read(request, p, "count", count.id)


@router.put("/counts/{doc_id}/lines", response_model=StockDocument)
async def enter_counted(
    doc_id: uuid.UUID, body: CountedIn, request: Request, p: CountCreate
) -> StockDocument:
    await _scoped(request, p, "count", doc_id)
    async with _db(request, p) as db:
        await counts.enter_counted(db, user_id=p.user_id, count_id=doc_id, data=body)
    return await _read(request, p, "count", doc_id)


@router.post("/counts/{doc_id}/submit", response_model=StockDocument)
async def submit_count(doc_id: uuid.UUID, request: Request, p: CountCreate) -> StockDocument:
    await _scoped(request, p, "count", doc_id)
    async with _db(request, p) as db:
        await counts.submit_count(db, user_id=p.user_id, count_id=doc_id)
    return await _read(request, p, "count", doc_id)


@router.post("/counts/{doc_id}/{decision}", response_model=StockDocument)
async def decide_count(
    doc_id: uuid.UUID, decision: Decision, request: Request, p: CountApprove
) -> StockDocument:
    await _scoped(request, p, "count", doc_id)
    async with _db(request, p) as db:
        await counts.decide_count(
            db, user_id=p.user_id, role_id=p.role_id, count_id=doc_id, approve=decision == "approve"
        )
    return await _read(request, p, "count", doc_id)
