"""Catalog endpoints (FR-CAT-001, 002, 004, 008, 009). Language for names comes from the `lang`
query parameter (the UI sends its current language); missing names fall back to the tenant
default language."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.idempotency import (
    idempotency_key,
    remember,
    replay_or_none,
    request_fingerprint,
)
from app.core.pagination import Page, PageParams, page_params
from app.core.tenancy import tenant_session
from app.modules.catalog import categories, prices, service
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Item
from app.modules.catalog.schemas import (
    CategoryIn,
    CategoryOut,
    ChannelIn,
    ChannelOut,
    EffectivePrice,
    ItemIn,
    ItemOut,
    ItemSummary,
    ItemUpdate,
    Language,
    PriceIn,
    PriceOut,
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


def _visible(p: Principal, item: ItemOut) -> ItemOut:
    """docs/03 rule 5: cost data is hidden from roles without catalog.cost.view, in the API too."""
    if not p.can(perm.COST_VIEW):
        item.standard_cost = None
        item.target_food_cost_bp = None
    return item


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
        rows = await categories.list_categories(db)
        return [CategoryOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryIn, request: Request, p: Update) -> CategoryOut:
    async with _db(request, p) as db:
        row = await categories.save_category(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body
        )
        return CategoryOut.model_validate(row, from_attributes=True)


@router.put("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID, body: CategoryIn, request: Request, p: Update
) -> CategoryOut:
    async with _db(request, p) as db:
        row = await categories.save_category(
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
        return _visible(
            p, await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)
        )


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
        out = _visible(
            p, await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)
        )
        if key:
            await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
    return out


@router.put("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID, body: ItemUpdate, request: Request, p: Update, lang: Lang = "en"
) -> ItemOut:
    async with _db(request, p) as db:
        if not p.can(perm.COST_VIEW):
            # They never saw the standard cost, so their save must not change or clear it.
            kept = (
                await db.execute(
                    select(Item.standard_cost, Item.target_food_cost_bp).where(Item.id == item_id)
                )
            ).first()
            body.standard_cost, body.target_food_cost_bp = kept if kept else (None, None)
        await service.update_item(
            db, tenant_id=p.tenant_id, user_id=p.user_id, item_id=item_id, data=body, language=lang
        )
        return _visible(
            p, await service.get_item(db, tenant_id=p.tenant_id, item_id=item_id, language=lang)
        )


# ─── Channels and prices (FR-CAT-004) ─────────────────────────────────────
# docs/03 has one row for "Edit items, menu, recipes, prices", so prices reuse the item
# permissions (and no new permission needs back-filling into existing tenants' roles).


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(
    request: Request, p: View, include_inactive: bool = False
) -> list[ChannelOut]:
    async with _db(request, p) as db:
        rows = await prices.list_channels(db, include_inactive=include_inactive)
        return [ChannelOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/channels", response_model=ChannelOut, status_code=201)
async def create_channel(body: ChannelIn, request: Request, p: Update) -> ChannelOut:
    async with _db(request, p) as db:
        row = await prices.save_channel(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return ChannelOut.model_validate(row, from_attributes=True)


@router.put("/channels/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: uuid.UUID, body: ChannelIn, request: Request, p: Update
) -> ChannelOut:
    async with _db(request, p) as db:
        row = await prices.save_channel(
            db, tenant_id=p.tenant_id, user_id=p.user_id, data=body, channel_id=channel_id
        )
        return ChannelOut.model_validate(row, from_attributes=True)


@router.get("/items/{item_id}/prices", response_model=list[PriceOut])
async def price_history(item_id: uuid.UUID, request: Request, p: View) -> list[PriceOut]:
    async with _db(request, p) as db:
        return await prices.price_history(db, item_id)


@router.put("/items/{item_id}/prices", response_model=PriceOut)
async def set_price(item_id: uuid.UUID, body: PriceIn, request: Request, p: Update) -> PriceOut:
    # PUT keyed by (channel, start date) is naturally idempotent: a retry saves the same row.
    async with _db(request, p) as db:
        return await prices.set_price(
            db, tenant_id=p.tenant_id, user_id=p.user_id, item_id=item_id, data=body
        )


@router.delete("/prices/{price_id}", status_code=204)
async def delete_price(price_id: uuid.UUID, request: Request, p: Update) -> Response:
    async with _db(request, p) as db:
        await prices.delete_price(db, tenant_id=p.tenant_id, user_id=p.user_id, price_id=price_id)
    return Response(status_code=204)


@router.get("/prices", response_model=Page[EffectivePrice])
async def effective_prices(
    request: Request,
    p: View,
    params: Annotated[PageParams, Depends(page_params)],
    channel_id: uuid.UUID,
    on: date | None = None,
) -> Page[EffectivePrice]:
    async with _db(request, p) as db:
        rows, cursor = await prices.effective_prices(
            db, tenant_id=p.tenant_id, channel_id=channel_id, on=on, params=params
        )
    return Page(items=rows, next_cursor=cursor)
