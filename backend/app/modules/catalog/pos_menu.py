"""The menu as the till sees it (FR-SAL-004): active menu items with today's price on a
channel, photo, sold-out flag and the modifier groups they offer, in one call. Items without
a price on the channel are left out, because they cannot be sold there."""

import uuid
from decimal import Decimal
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
from app.modules.catalog.outlet_menu import combo_parts, sold_out_at
from app.modules.catalog.prices import channel_code, prices_on, tenant_today


class ComboLine(BaseModel):
    item_id: uuid.UUID
    name: str
    qty: Decimal


class MenuItemOut(BaseModel):
    id: uuid.UUID
    name: str
    sku: str
    category_id: uuid.UUID | None
    photo_upload_id: uuid.UUID | None
    is_available: bool
    price: int
    modifier_groups: list[GroupOut]
    combo: list[ComboLine] = []  # FR-CAT-011: what the combo includes


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]


@router.get("/menu", response_model=list[MenuItemOut])
async def menu(
    channel_id: uuid.UUID,
    request: Request,
    p: View,
    lang: Literal["en", "id"] = "en",
    outlet_id: uuid.UUID | None = None,
) -> list[MenuItemOut]:
    """With an outlet: its own prices and sold-out switches (FR-TEN-011)."""
    if outlet_id is not None:
        p.require_outlet(outlet_id)
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
        prices = await prices_on(
            db, channel_id, ids, await tenant_today(db, p.tenant_id), outlet_id
        )
        off = await sold_out_at(db, outlet_id, ids) if outlet_id else set()
        parts = await combo_parts(db, set(prices))
        names = await item_names(db, p.tenant_id, lang, set(prices) | ids)
        groups = await groups_for_items(db, set(prices))
        items = [
            MenuItemOut(
                id=r.id,
                name=names[r.id].name,
                sku=names[r.id].sku,
                category_id=r.category_id,
                photo_upload_id=r.photo_upload_id,
                is_available=r.is_available and r.id not in off,
                combo=[
                    ComboLine(item_id=c, name=names[c].name if c in names else "", qty=q)
                    for c, q in parts.get(r.id, [])
                ],
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
