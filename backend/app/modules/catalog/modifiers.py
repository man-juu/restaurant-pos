"""Modifiers and availability (FR-CAT-003): groups of options with a price change and an
optional ingredient change, offered on menu items; and the "sold out" switch.

Options keep their id when a group is saved again, and options left out are switched off
rather than deleted, because sold order lines keep pointing at them (docs/05 2.6)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import tenant_session
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Item, ItemModifierGroup, ModifierGroup, ModifierOption

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Delta = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]


class OptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID | None = None  # keep an existing option
    name: Name
    price_delta: int = Field(default=0, ge=-(10**12), le=10**12)
    ingredient_item_id: uuid.UUID | None = None
    ingredient_qty: Delta | None = None  # base unit; negative = "without"
    is_active: bool = True

    @model_validator(mode="after")
    def ingredient_pair(self) -> "OptionIn":
        if (self.ingredient_item_id is None) != (self.ingredient_qty is None):
            raise ValueError("ingredient_item_id and ingredient_qty go together")
        if self.ingredient_qty == 0:
            raise ValueError("ingredient_qty must not be 0")
        return self


class GroupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    min_select: int = Field(default=0, ge=0, le=20)
    max_select: int = Field(default=1, ge=1, le=20)
    is_active: bool = True
    options: list[OptionIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def selects(self) -> "GroupIn":
        if self.min_select > self.max_select:
            raise ValueError("min_select is above max_select")
        return self


class OptionOut(OptionIn):
    id: uuid.UUID


class GroupOut(GroupIn):
    id: uuid.UUID
    options: list[OptionOut]  # type: ignore[assignment]


class ItemGroupsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_ids: list[uuid.UUID] = Field(max_length=20)


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_available: bool


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]
Availability = Annotated[Principal, Depends(require(perm.AVAILABILITY))]


async def _groups(db: AsyncSession, ids: set[uuid.UUID] | None = None) -> list[GroupOut]:
    stmt = select(ModifierGroup).order_by(ModifierGroup.name)
    if ids is not None:
        stmt = stmt.where(ModifierGroup.id.in_(ids))
    groups = list(await db.scalars(stmt))
    opts = await db.scalars(
        select(ModifierOption)
        .where(ModifierOption.group_id.in_([g.id for g in groups]))
        .order_by(ModifierOption.sort_order, ModifierOption.name)
    )
    by_group: dict[uuid.UUID, list[OptionOut]] = {}
    for o in opts:
        by_group.setdefault(o.group_id, []).append(
            OptionOut.model_validate(o, from_attributes=True)
        )
    return [
        GroupOut(
            id=g.id,
            name=g.name,
            min_select=g.min_select,
            max_select=g.max_select,
            is_active=g.is_active,
            options=by_group.get(g.id, []),
        )
        for g in groups
    ]


async def _check_ingredients(db: AsyncSession, options: list[OptionIn]) -> None:
    ids = {o.ingredient_item_id for o in options if o.ingredient_item_id}
    if not ids:
        return
    stmt = select(Item.id).where(Item.id.in_(ids), Item.is_stocked, Item.type != "menu")
    if missing := ids - set(await db.scalars(stmt)):
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, missing))})


async def _save_options(db: AsyncSession, group: ModifierGroup, options: list[OptionIn]) -> None:
    existing = {
        o.id: o
        for o in await db.scalars(select(ModifierOption).where(ModifierOption.group_id == group.id))
    }
    if unknown := {o.id for o in options if o.id} - existing.keys():
        raise NotFoundError("option_not_found", details={"ids": sorted(map(str, unknown))})
    kept: set[uuid.UUID] = set()
    for order, data in enumerate(options):
        values = data.model_dump(exclude={"id"}) | {"sort_order": order}
        row = existing.get(data.id) if data.id else None
        if row is None:
            row = ModifierOption(tenant_id=group.tenant_id, group_id=group.id, **values)
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            kept.add(row.id)
    for gone in existing.keys() - kept:
        existing[gone].is_active = False


async def save_group(
    db: AsyncSession, p: Principal, data: GroupIn, group_id: uuid.UUID | None = None
) -> GroupOut:
    await _check_ingredients(db, data.options)
    fields = data.model_dump(exclude={"options"})
    if group_id is None:
        group = ModifierGroup(tenant_id=p.tenant_id, **fields)
        db.add(group)
    else:
        found = await db.get(ModifierGroup, group_id, with_for_update=True)
        if found is None:
            raise NotFoundError("modifier_group_not_found")
        group = found
        for key, value in fields.items():
            setattr(group, key, value)
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("modifier_group_name_taken") from None
    await _save_options(db, group, data.options)
    await db.flush()
    await audit.record(
        db,
        tenant_id=p.tenant_id,
        user_id=p.user_id,
        action="catalog.modifier.update" if group_id else "catalog.modifier.create",
        target_type="modifier_group",
        target_id=group.id,
        summary={"name": group.name, "options": len(data.options)},
    )
    [out] = await _groups(db, {group.id})
    return out


@router.get("/modifier-groups", response_model=list[GroupOut])
async def list_groups(request: Request, p: View) -> list[GroupOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await _groups(db)


@router.post("/modifier-groups", response_model=GroupOut, status_code=201)
async def create_group(body: GroupIn, request: Request, p: Update) -> GroupOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await save_group(db, p, body)


@router.put("/modifier-groups/{group_id}", response_model=GroupOut)
async def update_group(group_id: uuid.UUID, body: GroupIn, request: Request, p: Update) -> GroupOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await save_group(db, p, body, group_id)


async def _menu_item(db: AsyncSession, item_id: uuid.UUID) -> Item:
    item = await db.get(Item, item_id)
    if item is None:
        raise NotFoundError("item_not_found")
    return item


@router.get("/items/{item_id}/modifier-groups", response_model=list[GroupOut])
async def item_groups(item_id: uuid.UUID, request: Request, p: View) -> list[GroupOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await _menu_item(db, item_id)
        return (await groups_for_items(db, {item_id})).get(item_id, [])


@router.put("/items/{item_id}/modifier-groups", response_model=list[GroupOut])
async def set_item_groups(
    item_id: uuid.UUID, body: ItemGroupsIn, request: Request, p: Update
) -> list[GroupOut]:
    if len(body.group_ids) != len(set(body.group_ids)):
        raise ConflictError("duplicate_modifier_group")
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        item = await _menu_item(db, item_id)
        if item.type != "menu":
            raise ConflictError("not_a_menu_item")
        found = set(
            await db.scalars(select(ModifierGroup.id).where(ModifierGroup.id.in_(body.group_ids)))
        )
        if missing := set(body.group_ids) - found:
            raise NotFoundError(
                "modifier_group_not_found", details={"ids": sorted(map(str, missing))}
            )
        await db.execute(delete(ItemModifierGroup).where(ItemModifierGroup.item_id == item_id))
        if body.group_ids:
            rows = [
                {"tenant_id": p.tenant_id, "item_id": item_id, "group_id": g, "sort_order": i}
                for i, g in enumerate(body.group_ids)
            ]
            await db.execute(insert(ItemModifierGroup), rows)
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="catalog.modifier.assign",
            target_type="item",
            target_id=item_id,
            summary={"groups": [str(g) for g in body.group_ids]},
        )
        return (await groups_for_items(db, {item_id})).get(item_id, [])


@router.put("/items/{item_id}/availability", status_code=204)
async def set_availability(
    item_id: uuid.UUID, body: AvailabilityIn, request: Request, p: Availability
) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        item = await _menu_item(db, item_id)
        item.is_available = body.is_available
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="catalog.item.availability",
            target_type="item",
            target_id=item_id,
            summary={"is_available": body.is_available},
        )


async def groups_for_items(
    db: AsyncSession, item_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[GroupOut]]:
    links = list(
        await db.scalars(
            select(ItemModifierGroup)
            .where(ItemModifierGroup.item_id.in_(item_ids))
            .order_by(ItemModifierGroup.sort_order)
        )
    )
    groups = {g.id: g for g in await _groups(db, {ln.group_id for ln in links})}
    out: dict[uuid.UUID, list[GroupOut]] = {}
    for ln in links:
        out.setdefault(ln.item_id, []).append(groups[ln.group_id])
    return out


@dataclass(frozen=True)
class SaleOption:
    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    price_delta: int
    ingredient_item_id: uuid.UUID | None
    ingredient_qty: Decimal | None


@dataclass(frozen=True)
class SaleGroup:
    id: uuid.UUID
    name: str
    min_select: int
    max_select: int
    options: dict[uuid.UUID, SaleOption]


async def sale_groups(
    db: AsyncSession, item_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[SaleGroup]]:
    """For the POS: the active groups and options each menu item offers today."""
    out: dict[uuid.UUID, list[SaleGroup]] = {}
    for item_id, groups in (await groups_for_items(db, item_ids)).items():
        out[item_id] = [
            SaleGroup(
                id=g.id,
                name=g.name,
                min_select=g.min_select,
                max_select=g.max_select,
                options={
                    o.id: SaleOption(
                        o.id, g.id, o.name, o.price_delta, o.ingredient_item_id, o.ingredient_qty
                    )
                    for o in g.options
                    if o.is_active
                },
            )
            for g in groups
            if g.is_active
        ]
    return out


async def option_ingredients(
    db: AsyncSession, option_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, Decimal]]:
    """Ingredient change per option (item, base quantity), for options that have one. Reads
    switched-off options too: a line sold before the switch keeps its recipe change."""
    stmt = select(
        ModifierOption.id, ModifierOption.ingredient_item_id, ModifierOption.ingredient_qty
    ).where(ModifierOption.id.in_(option_ids), ModifierOption.ingredient_item_id.is_not(None))
    rows = (await db.execute(stmt)).all()
    return {r[0]: (r[1], r[2]) for r in rows if r[1] is not None and r[2] is not None}
