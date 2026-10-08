"""Catalog service (FR-CAT-001, 002, 008, 009). Runs inside tenant_session, so RLS limits every
query to the caller's tenant. Foreign keys are checked by PostgreSQL without RLS, so references
to units and categories are looked up here first: a row another tenant owns is "not found"."""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core import audit
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.models import Tenant
from app.core.pagination import PageParams, paginate
from app.modules.catalog.models import (
    Item,
    ItemCategory,
    ItemTranslation,
    ItemUnitConversion,
    Unit,
)
from app.modules.catalog.schemas import (
    CategoryIn,
    ItemIn,
    ItemOut,
    ItemSummary,
    ItemUpdate,
    UnitIn,
    UnitOut,
)

# Exact factors to each dimension's base unit for platform units (physics, not tax policy).
PLATFORM_FACTORS = {"g": Decimal(1), "kg": Decimal(1000), "ml": Decimal(1), "l": Decimal(1000)}


class InvalidCatalogReference(AppError):
    status_code, code = 422, "invalid_reference"


class NoConversion(AppError):
    status_code, code = 422, "no_unit_conversion"


# ─── Units ────────────────────────────────────────────────────────────────


def _unit_out(u: Unit) -> UnitOut:
    return UnitOut.model_validate(
        {
            "id": u.id,
            "code": u.code,
            "name": u.name,
            "dimension": u.dimension,
            "is_platform": u.tenant_id is None,
        }
    )


async def list_units(db: AsyncSession) -> list[UnitOut]:
    rows = (await db.execute(select(Unit).order_by(Unit.dimension, Unit.code))).scalars()
    return [_unit_out(u) for u in rows]


async def create_unit(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: UnitIn
) -> UnitOut:
    clash = await db.scalar(select(Unit.id).where(func.lower(Unit.code) == data.code.lower()))
    if clash:
        raise ConflictError("unit_code_taken")
    unit = Unit(tenant_id=tenant_id, **data.model_dump())
    db.add(unit)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.unit.create",
        target_type="unit",
        target_id=unit.id,
        summary=data.model_dump(),
    )
    return _unit_out(unit)


async def _visible_units(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Unit]:
    rows = (await db.execute(select(Unit).where(Unit.id.in_(ids)))).scalars()
    found = {u.id: u for u in rows}
    if missing := ids - found.keys():
        raise InvalidCatalogReference(details={"unit_ids": sorted(map(str, missing))})
    return found


def platform_factor(from_unit: Unit, to_unit: Unit) -> Decimal | None:
    """kg -> g = 1000 and similar; None if either unit is not a platform mass/volume unit."""
    if from_unit.dimension != to_unit.dimension:
        return None
    a, b = PLATFORM_FACTORS.get(from_unit.code), PLATFORM_FACTORS.get(to_unit.code)
    if from_unit.tenant_id or to_unit.tenant_id or a is None or b is None:
        return None
    return a / b


async def factor_to_base(db: AsyncSession, item_id: uuid.UUID, unit_id: uuid.UUID) -> Decimal:
    """FR-CAT-002: how many base units one `unit_id` of this item is. Exact."""
    item = await db.get(Item, item_id)
    if item is None:
        raise NotFoundError("item_not_found")
    if unit_id == item.base_unit_id:
        return Decimal(1)
    explicit = await db.scalar(
        select(ItemUnitConversion.factor_to_base).where(
            ItemUnitConversion.item_id == item_id, ItemUnitConversion.unit_id == unit_id
        )
    )
    if explicit is not None:
        return explicit
    units = await _visible_units(db, {unit_id, item.base_unit_id})
    factor = platform_factor(units[unit_id], units[item.base_unit_id])
    if factor is None:
        raise NoConversion(details={"item_id": str(item_id), "unit_id": str(unit_id)})
    return factor


# ─── Categories ───────────────────────────────────────────────────────────


async def list_categories(db: AsyncSession) -> list[ItemCategory]:
    stmt = select(ItemCategory).order_by(ItemCategory.sort_order, ItemCategory.name)
    return list((await db.execute(stmt)).scalars())


async def _check_parent(
    db: AsyncSession, parent_id: uuid.UUID | None, self_id: uuid.UUID | None = None
) -> None:
    """Parent must exist in this tenant and must not create a loop."""
    seen = {self_id} if self_id else set()
    current = parent_id
    while current is not None:
        if current in seen:
            raise InvalidCatalogReference("category_cycle")
        seen.add(current)
        current_row = await db.get(ItemCategory, current)
        if current_row is None:
            raise InvalidCatalogReference(details={"parent_id": str(parent_id)})
        current = current_row.parent_id
        if len(seen) > 20:
            raise InvalidCatalogReference("category_too_deep")


async def save_category(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: CategoryIn,
    category_id: uuid.UUID | None = None,
) -> ItemCategory:
    await _check_parent(db, data.parent_id, category_id)
    if category_id is None:
        row = ItemCategory(tenant_id=tenant_id, **data.model_dump())
        db.add(row)
        action, before = "catalog.category.create", None
    else:
        found = await db.get(ItemCategory, category_id)
        if found is None:
            raise NotFoundError("category_not_found")
        row = found
        before = CategoryIn.model_validate(row, from_attributes=True).model_dump(mode="json")
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        action = "catalog.category.update"
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("category_name_taken") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        target_type="item_category",
        target_id=row.id,
        summary={"before": before, "after": data.model_dump(mode="json")},
    )
    return row


# ─── Items ────────────────────────────────────────────────────────────────


async def _default_language(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    return (await db.scalar(select(Tenant.language).where(Tenant.id == tenant_id))) or "en"


async def list_items(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    language: str,
    params: PageParams,
    item_type: str | None = None,
    category_id: uuid.UUID | None = None,
    search: str | None = None,
    include_inactive: bool = False,
) -> tuple[list[ItemSummary], str | None]:
    default_language = await _default_language(db, tenant_id)
    want, fallback = aliased(ItemTranslation), aliased(ItemTranslation)
    name = func.coalesce(want.name, fallback.name, Item.sku)
    stmt = (
        select(Item, name.label("name"))
        .outerjoin(want, (want.item_id == Item.id) & (want.language == language))
        .outerjoin(
            fallback, (fallback.item_id == Item.id) & (fallback.language == default_language)
        )
    )
    if not include_inactive:
        stmt = stmt.where(Item.is_active)
    if item_type:
        stmt = stmt.where(Item.type == item_type)
    if category_id:
        stmt = stmt.where(Item.category_id == category_id)
    if search:
        pattern = "%" + search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        matches = select(ItemTranslation.item_id).where(ItemTranslation.name.ilike(pattern))
        stmt = stmt.where(or_(Item.sku.ilike(pattern), Item.id.in_(matches)))
    rows, cursor = await paginate(
        db,
        cast(Select[Any], stmt),
        params,
        id_column=cast(ColumnElement[Any], Item.id),
        sortable={"sku": cast(ColumnElement[Any], Item.sku), "name": name},
        default_sort="name",
    )
    return [_summary(item, row_name) for item, row_name in rows], cursor


def _summary(item: Item, name: str) -> ItemSummary:
    return ItemSummary(
        id=item.id,
        sku=item.sku,
        type=item.type,  # type: ignore[arg-type]
        name=name,
        category_id=item.category_id,
        base_unit_id=item.base_unit_id,
        is_active=item.is_active,
        photo_upload_id=item.photo_upload_id,
    )


async def get_item(
    db: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, language: str
) -> ItemOut:
    item = await db.get(Item, item_id)
    if item is None:
        raise NotFoundError("item_not_found")
    translations = (
        (await db.execute(select(ItemTranslation).where(ItemTranslation.item_id == item_id)))
        .scalars()
        .all()
    )
    conversions = (
        (await db.execute(select(ItemUnitConversion).where(ItemUnitConversion.item_id == item_id)))
        .scalars()
        .all()
    )
    by_lang = {t.language: t.name for t in translations}
    name = by_lang.get(language) or by_lang.get(await _default_language(db, tenant_id))
    return ItemOut(
        **_summary(item, name or next(iter(by_lang.values()), item.sku)).model_dump(),
        is_stocked=item.is_stocked,
        tracking_mode=item.tracking_mode,
        standard_cost=item.standard_cost,
        shelf_life_days=item.shelf_life_days,
        storage_type=item.storage_type,
        allergens=list(item.allergens),
        version=item.version,
        translations=[
            {"language": t.language, "name": t.name, "description": t.description}  # type: ignore[misc]
            for t in sorted(translations, key=lambda t: t.language)
        ],
        conversions=[
            {"unit_id": c.unit_id, "factor_to_base": c.factor_to_base}  # type: ignore[misc]
            for c in sorted(conversions, key=lambda c: str(c.unit_id))
        ],
    )


async def _check_item_refs(db: AsyncSession, data: ItemIn) -> None:
    unit_ids = {data.base_unit_id, *(c.unit_id for c in data.conversions)}
    await _visible_units(db, unit_ids)
    if data.base_unit_id in {c.unit_id for c in data.conversions}:
        raise InvalidCatalogReference("conversion_to_base_unit")
    if data.category_id and await db.get(ItemCategory, data.category_id) is None:
        raise InvalidCatalogReference(details={"category_id": str(data.category_id)})


async def _replace_children(
    db: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, data: ItemIn
) -> None:
    await db.execute(delete(ItemTranslation).where(ItemTranslation.item_id == item_id))
    await db.execute(delete(ItemUnitConversion).where(ItemUnitConversion.item_id == item_id))
    await db.execute(
        insert(ItemTranslation),
        [{"tenant_id": tenant_id, "item_id": item_id, **t.model_dump()} for t in data.translations],
    )
    if data.conversions:
        await db.execute(
            insert(ItemUnitConversion),
            [
                {"tenant_id": tenant_id, "item_id": item_id, **c.model_dump()}
                for c in data.conversions
            ],
        )


_ITEM_FIELDS: Sequence[str] = (
    "sku",
    "type",
    "category_id",
    "base_unit_id",
    "is_stocked",
    "tracking_mode",
    "standard_cost",
    "shelf_life_days",
    "storage_type",
    "allergens",
)


async def create_item(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: ItemIn
) -> uuid.UUID:
    await _check_item_refs(db, data)
    if await db.scalar(select(Item.id).where(Item.sku == data.sku)):
        raise ConflictError("sku_taken")
    item = Item(
        tenant_id=tenant_id,
        created_by=user_id,
        updated_by=user_id,
        **{f: getattr(data, f) for f in _ITEM_FIELDS},
    )
    db.add(item)
    await db.flush()
    await _replace_children(db, tenant_id, item.id, data)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.item.create",
        target_type="item",
        target_id=item.id,
        summary={"after": data.model_dump(mode="json")},
    )
    return item.id


async def update_item(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemUpdate,
    language: str,
) -> None:
    item = await db.get(Item, item_id, with_for_update=True)
    if item is None:
        raise NotFoundError("item_not_found")
    if item.version != data.version:
        # Someone else saved first: the client must reload instead of overwriting their change.
        raise ConflictError("stale_version", details={"current_version": item.version})
    if item.base_unit_id != data.base_unit_id:
        # Changing the base unit would silently rescale every quantity already recorded.
        raise ConflictError("base_unit_locked")
    await _check_item_refs(db, data)
    if data.sku != item.sku and await db.scalar(select(Item.id).where(Item.sku == data.sku)):
        raise ConflictError("sku_taken")
    before = (
        await get_item(db, tenant_id=tenant_id, item_id=item_id, language=language)
    ).model_dump(mode="json")
    for f in (*_ITEM_FIELDS, "is_active"):
        setattr(item, f, getattr(data, f))
    item.updated_by = user_id
    item.updated_at = func.now()
    await db.flush()
    await _replace_children(db, tenant_id, item_id, data)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.item.update",
        target_type="item",
        target_id=item_id,
        summary={"before": before, "after": data.model_dump(mode="json")},
    )
