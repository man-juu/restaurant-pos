"""Catalog endpoints (FR-CAT-001, 002, 008, 009). Language for names comes from the `lang`
query parameter (the UI sends its current language); missing names fall back to the tenant
default language."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    idempotency_key,
    remember,
    replay_or_none,
    request_fingerprint,
)
from app.core.pagination import Page, PageParams, page_params
from app.core.tenancy import tenant_session
from app.modules.catalog import permissions as perm
from app.modules.catalog import service
from app.modules.catalog.schemas import (
    CategoryIn,
    CategoryOut,
    ItemIn,
    ItemOut,
    ItemSummary,
    ItemUpdate,
    Language,
    UnitIn,
    UnitOut,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Create = Annotated[Principal, Depends(require(perm.ITEM_CREATE))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]
Lang = Annotated[Language, Query()]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/units", response_model=list[UnitOut])
async def list_units(request: Request, p: View) -> list[UnitOut]:
    async with _db(request, p) as db:
        return await service.list_units(db)


@router.post("/units", response_model=UnitOut, status_code=201)
async def create_unit(body: UnitIn, request: Request, p: Update) -> UnitOut:
    async with _db(request, p) as db:
        return await service.create_unit(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(request: Request, p: View) -> list[CategoryOut]:
    async with _db(request, p) as db:
        rows = await service.list_categories(db)
        return [CategoryOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryIn, request: Request, p: Update) -> CategoryOut:
    async with _db(request, p) as db:
        row = await service.save_category(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return CategoryOut.model_validate(row, from_attributes=True)


@router.put("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID, body: CategoryIn, request: Request, p: Update
) -> CategoryOut:
    async with _db(request, p) as db:
        row = await service.save_category(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, category_id=category_id
        )
        return CategoryOut.model_validate(row, from_attributes=True)


@router.get("/items", response_model=Page[ItemSummary])
async def list_items(
    request: Request,
    p: View,
    params: Annotated[PageParams, Depends(page_params)],
    lang: Lang = "en",
    type: Literal["ingredient", "semi_finished", "menu"] | None = None,
    category_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_inactive: bool = False,
) -> Page[ItemSummary]:
    async with _db(request, p) as db:
        items, cursor = await service.list_items(
            db,
            tenant_id=p.tenant_id,
            language=lang,
            params=params,
            item_type=type,
            category_id=category_id,
            search=q,
            include_inactive=include_inactive,
        )
    return Page(items=items, next_cursor=cursor)


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: uuid.UUID, request: Request, p: View, lang: Lang = "en") -> ItemOut:
    async with _db(request, p) as db:
        return await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)


@router.post("/items", response_model=ItemOut, status_code=201)
async def create_item(
    body: ItemIn,
    request: Request,
    p: Create,
    key: Annotated[uuid.UUID | None, Depends(idempotency_key)],
    lang: Lang = "en",
) -> ItemOut | JSONResponse:
    fingerprint = await request_fingerprint(request) if key else ""
    async with _db(request, p) as db:
        if key and (stored := await replay_or_none(db, key, fingerprint)):
            return JSONResponse(stored.body, status_code=stored.status)
        item_id = await service.create_item(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)
        if key:
            await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
    return out


@router.put("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID, body: ItemUpdate, request: Request, p: Update, lang: Lang = "en"
) -> ItemOut:
    async with _db(request, p) as db:
        await service.update_item(
            db, tenant_id=p.tenant_id, user_id=p.user_id, item_id=item_id, data=body, language=lang
        )
        return await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)
