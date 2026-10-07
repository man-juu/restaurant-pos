"""Recipe endpoints (FR-CAT-005 to 007). docs/03: "Edit items, menu, recipes, prices" is one
row, so recipes reuse the item permissions; costs and margins also need catalog.cost.view."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog import boms, costing, prices
from app.modules.catalog import permissions as perm
from app.modules.catalog.schemas import BomActivate, BomIn, BomOut, BomSummary, Costing, Language

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]
Lang = Annotated[Language, Query()]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/items/{item_id}/boms", response_model=list[BomSummary])
async def list_versions(item_id: uuid.UUID, request: Request, p: View) -> list[BomSummary]:
    async with _db(request, p) as db:
        return await boms.list_versions(db, item_id)


@router.post("/items/{item_id}/boms", response_model=BomOut, status_code=201)
async def create_draft(
    item_id: uuid.UUID, body: BomIn, request: Request, p: Update, lang: Lang = "en"
) -> BomOut:
    async with _db(request, p) as db:
        bom_id = await boms.create_draft(
            db, tenant_id=p.tenant_id, user_id=p.user_id, item_id=item_id, data=body
        )
        return await boms.get_bom(db, tenant_id=p.tenant_id, bom_id=bom_id, language=lang)


@router.get("/boms/{bom_id}", response_model=BomOut)
async def get_bom(bom_id: uuid.UUID, request: Request, p: View, lang: Lang = "en") -> BomOut:
    async with _db(request, p) as db:
        return await boms.get_bom(db, tenant_id=p.tenant_id, bom_id=bom_id, language=lang)


@router.put("/boms/{bom_id}", response_model=BomOut)
async def update_draft(
    bom_id: uuid.UUID, body: BomIn, request: Request, p: Update, lang: Lang = "en"
) -> BomOut:
    async with _db(request, p) as db:
        await boms.update_draft(db, user_id=p.user_id, bom_id=bom_id, data=body)
        return await boms.get_bom(db, tenant_id=p.tenant_id, bom_id=bom_id, language=lang)


@router.delete("/boms/{bom_id}", status_code=204)
async def delete_draft(bom_id: uuid.UUID, request: Request, p: Update) -> Response:
    async with _db(request, p) as db:
        await boms.delete_draft(db, user_id=p.user_id, bom_id=bom_id)
    return Response(status_code=204)


@router.post("/boms/{bom_id}/activate", response_model=BomSummary)
async def activate(bom_id: uuid.UUID, body: BomActivate, request: Request, p: Update) -> BomSummary:
    async with _db(request, p) as db:
        return await boms.activate(db, user_id=p.user_id, bom_id=bom_id, valid_from=body.valid_from)


@router.get("/items/{item_id}/costing", response_model=Costing)
async def item_costing(
    item_id: uuid.UUID, request: Request, p: View, on: date | None = None, lang: Lang = "en"
) -> Costing:
    async with _db(request, p) as db:
        day = on or await prices.tenant_today(db, p.tenant_id)
        return await costing.costing(
            db,
            tenant_id=p.tenant_id,
            item_id=item_id,
            on=day,
            language=lang,
            show_cost=p.can(perm.COST_VIEW),
        )
