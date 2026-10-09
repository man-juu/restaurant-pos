"""The menu as the till sees it (FR-SAL-004): active menu items with today's price on a
channel, photo, sold-out flag and the modifier groups they offer, in one call. Items without
a price on the channel are left out, because they cannot be sold there."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog import permissions as perm
from app.modules.catalog.boms import item_names
from app.modules.catalog.models import Item
from app.modules.catalog.modifiers import GroupOut, groups_for_items
from app.modules.catalog.prices import channel_code, prices_on, tenant_today


class MenuItemOut(BaseModel):
    id: uuid.UUID
    name: str
    sku: str
    category_id: uuid.UUID | None
    photo_upload_id: uuid.UUID | None
    is_available: bool
    price: int
    modifier_groups: list[GroupOut]


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]


@router.get("/menu", response_model=list[MenuItemOut])
async def menu(
    channel_id: uuid.UUID, request: Request, p: View, lang: Literal["en", "id"] = "en"
) -> list[MenuItemOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await channel_code(db, channel_id)  # an active channel of this tenant
        rows = (
            await db.execute(
                select(Item.id, Item.category_id, Item.photo_upload_id, Item.is_available).where(
                    Item.type == "menu", Item.is_active
                )
            )
        ).all()
        ids = {r.id for r in rows}
        prices = await prices_on(db, channel_id, ids, await tenant_today(db, p.tenant_id))
        names = await item_names(db, p.tenant_id, lang, prices.keys())
        groups = await groups_for_items(db, set(prices))
        items = [
            MenuItemOut(
                id=r.id,
                name=names[r.id].name,
                sku=names[r.id].sku,
                category_id=r.category_id,
                photo_upload_id=r.photo_upload_id,
                is_available=r.is_available,
                price=prices[r.id],
                modifier_groups=[
                    g.model_copy(update={"options": [o for o in g.options if o.is_active]})
                    for g in groups.get(r.id, [])
                    if g.is_active
                ],
            )
            for r in rows
            if r.id in prices
        ]
        return sorted(items, key=lambda i: i.name.lower())
