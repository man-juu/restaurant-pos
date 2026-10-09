"""Per-outlet menu (FR-TEN-011) and combos (FR-CAT-011). The master menu is shared; an
outlet may mark an item sold out on its own. A combo is a menu item sold at its own price
whose stock comes from the menu items in it."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Outlet
from app.core.tenancy import tenant_session
from app.modules.catalog import permissions as perm
from app.modules.catalog.menu_models import ComboComponent, OutletItemOverride
from app.modules.catalog.models import Item

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]
Availability = Annotated[Principal, Depends(require(perm.AVAILABILITY))]


class OutletAvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_available: bool


class ComboPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: Annotated[Decimal, Field(gt=0, le=100, max_digits=18, decimal_places=4)] = Decimal(1)


class ComboIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[ComboPart] = Field(max_length=20)  # empty: no longer a combo


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _item(db: AsyncSession, item_id: uuid.UUID) -> Item:
    item = await db.get(Item, item_id)
    if item is None:
        raise NotFoundError("item_not_found")
    return item


@router.put("/items/{item_id}/outlets/{outlet_id}/availability", status_code=204)
async def set_outlet_availability(
    item_id: uuid.UUID,
    outlet_id: uuid.UUID,
    body: OutletAvailabilityIn,
    request: Request,
    p: Availability,
) -> None:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await _item(db, item_id)
        if await db.get(Outlet, outlet_id) is None:
            raise NotFoundError("outlet_not_found")
        row = await db.get(OutletItemOverride, (p.tenant_id, outlet_id, item_id))
        if row is None:
            db.add(
                OutletItemOverride(
                    tenant_id=p.tenant_id,
                    outlet_id=outlet_id,
                    item_id=item_id,
                    is_available=body.is_available,
                )
            )
        else:
            row.is_available = body.is_available
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            outlet_id=outlet_id,
            action="catalog.item.outlet_availability",
            target_type="item",
            target_id=item_id,
            summary={"is_available": body.is_available},
        )


async def sold_out_at(
    db: AsyncSession, outlet_id: uuid.UUID, ids: set[uuid.UUID]
) -> set[uuid.UUID]:
    """Items this outlet marked sold out (the master switch is checked separately)."""
    stmt = select(OutletItemOverride.item_id).where(
        OutletItemOverride.outlet_id == outlet_id,
        OutletItemOverride.item_id.in_(ids),
        OutletItemOverride.is_available.is_(False),
    )
    return set(await db.scalars(stmt))


@router.get("/items/{item_id}/combo", response_model=list[ComboPart])
async def get_combo(item_id: uuid.UUID, request: Request, p: View) -> list[ComboPart]:
    async with _db(request, p) as db:
        await _item(db, item_id)
        return [
            ComboPart(item_id=c, qty=q)
            for c, q in (await combo_parts(db, {item_id})).get(item_id, [])
        ]


@router.put("/items/{item_id}/combo", response_model=list[ComboPart])
async def set_combo(
    item_id: uuid.UUID, body: ComboIn, request: Request, p: Update
) -> list[ComboPart]:
    ids = [x.item_id for x in body.parts]
    if len(ids) != len(set(ids)) or item_id in ids:
        raise ConflictError("invalid_combo")
    async with _db(request, p) as db:
        if (await _item(db, item_id)).type != "menu":
            raise ConflictError("not_a_menu_item")
        found = list(await db.scalars(select(Item).where(Item.id.in_(ids))))
        if len(found) != len(ids) or any(i.type != "menu" for i in found):
            raise NotFoundError("item_not_found")
        # One level only: a combo cannot contain a combo (keeps stock and kitchen simple).
        if ids and await db.scalar(
            select(ComboComponent.combo_item_id)
            .where(ComboComponent.combo_item_id.in_(ids))
            .limit(1)
        ):
            raise ConflictError("combo_in_combo")
        if await db.scalar(
            select(ComboComponent.combo_item_id)
            .where(ComboComponent.component_item_id == item_id)
            .limit(1)
        ):
            raise ConflictError("combo_in_combo")
        await db.execute(delete(ComboComponent).where(ComboComponent.combo_item_id == item_id))
        if body.parts:
            await db.execute(
                insert(ComboComponent),
                [
                    {
                        "tenant_id": p.tenant_id,
                        "combo_item_id": item_id,
                        "component_item_id": x.item_id,
                        "qty": x.qty,
                        "sort_order": n,
                    }
                    for n, x in enumerate(body.parts)
                ],
            )
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="catalog.combo.set",
            target_type="item",
            target_id=item_id,
            summary={"parts": len(body.parts)},
        )
        return body.parts


async def combo_parts(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[uuid.UUID, Decimal]]]:
    stmt = (
        select(ComboComponent.combo_item_id, ComboComponent.component_item_id, ComboComponent.qty)
        .where(ComboComponent.combo_item_id.in_(ids))
        .order_by(ComboComponent.sort_order)
    )
    out: dict[uuid.UUID, list[tuple[uuid.UUID, Decimal]]] = {}
    for combo, part, qty in (await db.execute(stmt)).all():
        out.setdefault(combo, []).append((part, qty))
    return out


async def expand_combos(
    db: AsyncSession, quantities: dict[uuid.UUID, Decimal]
) -> dict[uuid.UUID, Decimal]:
    """Replace each combo by its parts (times how many combos), for stock consumption."""
    parts = await combo_parts(db, set(quantities))
    if not parts:
        return quantities
    out: dict[uuid.UUID, Decimal] = {}
    for item_id, qty in quantities.items():
        for part, part_qty in parts.get(item_id, [(item_id, Decimal(1))]):
            out[part] = out.get(part, Decimal(0)) + qty * part_qty
    return out
