"""Recipes / bills of materials (FR-CAT-005, FR-CAT-006, docs/05 section 2.2).

Versions: a draft is edited freely; activating it fixes its lines and gives it a start date,
and the previous active version ends the day before (one active recipe per item per date).
Sales and production record the version they used, so a fixed recipe never changes; to
change a recipe, copy it into a new draft.

Nesting: a menu item may use semi-finished items, which have their own recipes. Every save
checks all versions (draft or active) of the components, so no recipe can ever contain
itself, whatever is activated later.
"""

import uuid
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tenant
from app.modules.catalog.models import Bom, BomLine, Item, ItemTranslation, Unit
from app.modules.catalog.schemas import (
    BomIn,
    BomLineOut,
    BomOut,
    BomSummary,
)
from app.modules.catalog.service import InvalidCatalogReference
from app.modules.catalog.units import base_factors

MAX_DEPTH = 10  # nesting levels; deep enough for real kitchens, bounds every walk
COMPONENT_TYPES = frozenset({"ingredient", "semi_finished"})


# ─── Reading ──────────────────────────────────────────────────────────────


class ItemLabel(NamedTuple):
    sku: str
    name: str  # in the requested language, else the tenant language, else the SKU
    unit_code: str  # base unit


async def item_names(
    db: AsyncSession, tenant_id: uuid.UUID, language: str, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, ItemLabel]:
    default = (await db.scalar(select(Tenant.language).where(Tenant.id == tenant_id))) or "en"
    want, fallback = aliased(ItemTranslation), aliased(ItemTranslation)
    stmt = (
        select(Item.id, Item.sku, func.coalesce(want.name, fallback.name, Item.sku), Unit.code)
        .join(Unit, Unit.id == Item.base_unit_id)
        .outerjoin(want, (want.item_id == Item.id) & (want.language == language))
        .outerjoin(fallback, (fallback.item_id == Item.id) & (fallback.language == default))
        .where(Item.id.in_(set(ids)))
    )
    return {i: ItemLabel(sku, name, code) for i, sku, name, code in (await db.execute(stmt)).all()}


async def active_boms(db: AsyncSession, item_ids: set[uuid.UUID], on: date) -> dict[uuid.UUID, Bom]:
    """The recipe in force on `on` for each item that has one."""
    stmt = select(Bom).where(
        Bom.item_id.in_(item_ids),
        Bom.status == "active",
        Bom.valid_from <= on,
        or_(Bom.valid_to.is_(None), Bom.valid_to >= on),
    )
    return {b.item_id: b for b in (await db.execute(stmt)).scalars()}


def _summary(bom: Bom) -> BomSummary:
    return BomSummary.model_validate(bom, from_attributes=True)


async def list_versions(db: AsyncSession, item_id: uuid.UUID) -> list[BomSummary]:
    if await db.get(Item, item_id) is None:
        raise NotFoundError("item_not_found")
    stmt = select(Bom).where(Bom.item_id == item_id).order_by(Bom.version.desc())
    return [_summary(b) for b in (await db.execute(stmt)).scalars()]


async def get_bom(
    db: AsyncSession, *, tenant_id: uuid.UUID, bom_id: uuid.UUID, language: str
) -> BomOut:
    bom = await db.get(Bom, bom_id)
    if bom is None:
        raise NotFoundError("bom_not_found")
    lines = list(
        (await db.execute(select(BomLine).where(BomLine.bom_id == bom_id).order_by(BomLine.id)))
        .scalars()
        .all()
    )
    names = await item_names(db, tenant_id, language, (ln.component_item_id for ln in lines))
    return BomOut(
        **_summary(bom).model_dump(),
        lines=[
            BomLineOut(
                component_item_id=ln.component_item_id,
                component_sku=names[ln.component_item_id].sku,
                component_name=names[ln.component_item_id].name,
                qty=ln.qty,
                unit_id=ln.unit_id,
                waste_pct=ln.waste_pct,
            )
            for ln in lines
        ],
    )


# ─── Checks ───────────────────────────────────────────────────────────────


async def _check_components(db: AsyncSession, item: Item, data: BomIn) -> None:
    if item.type not in {"menu", "semi_finished"}:
        raise InvalidCatalogReference("ingredient_has_no_recipe")
    ids = {line.component_item_id for line in data.lines}
    # Looked up under RLS: another tenant's item is "not found" (foreign keys ignore RLS).
    found = dict((await db.execute(select(Item.id, Item.type).where(Item.id.in_(ids)))).all())
    if missing := ids - found.keys():
        raise InvalidCatalogReference(details={"component_ids": sorted(map(str, missing))})
    if wrong := [str(i) for i, kind in found.items() if kind not in COMPONENT_TYPES]:
        raise InvalidCatalogReference("component_not_stock_item", details={"ids": sorted(wrong)})
    await _check_cycle(db, item.id, ids)


async def _check_cycle(db: AsyncSession, root: uuid.UUID, components: set[uuid.UUID]) -> None:
    """Walk down through every version of every component; reaching `root` is a cycle."""
    seen: set[uuid.UUID] = set()
    frontier = components
    for _ in range(MAX_DEPTH):
        if root in frontier:
            raise InvalidCatalogReference("bom_cycle")
        seen |= frontier
        stmt = (
            select(BomLine.component_item_id)
            .join(Bom, Bom.id == BomLine.bom_id)
            .where(Bom.item_id.in_(frontier))
            .distinct()
        )
        frontier = set((await db.execute(stmt)).scalars()) - seen
        if not frontier:
            return
    raise InvalidCatalogReference("bom_too_deep")


async def _yield(db: AsyncSession, item: Item, data: BomIn) -> tuple[Decimal, uuid.UUID]:
    if data.yield_qty is None or data.yield_unit_id is None:
        if item.type == "semi_finished":
            raise InvalidCatalogReference("yield_required")
        return Decimal(1), item.base_unit_id
    return data.yield_qty, data.yield_unit_id


async def _validated(db: AsyncSession, item: Item, data: BomIn) -> tuple[Decimal, uuid.UUID]:
    await _check_components(db, item, data)
    qty, unit = await _yield(db, item, data)
    # Every quantity must convert to its item's base unit, or costing and stock would fail.
    pairs = {(ln.component_item_id, ln.unit_id) for ln in data.lines} | {(item.id, unit)}
    await base_factors(db, pairs)
    return qty, unit


# ─── Writing ──────────────────────────────────────────────────────────────


async def _locked_item(db: AsyncSession, item_id: uuid.UUID) -> Item:
    # Locking the item serialises version numbers and activations for that item.
    item = await db.get(Item, item_id, with_for_update=True)
    if item is None:
        raise NotFoundError("item_not_found")
    return item


async def _draft(db: AsyncSession, bom_id: uuid.UUID) -> Bom:
    bom = await db.get(Bom, bom_id, with_for_update=True)
    if bom is None:
        raise NotFoundError("bom_not_found")
    if bom.status != "draft":
        raise ConflictError("bom_not_draft")
    return bom


async def _write_lines(db: AsyncSession, bom: Bom, data: BomIn) -> None:
    await db.execute(delete(BomLine).where(BomLine.bom_id == bom.id))
    await db.execute(
        insert(BomLine),
        [{"tenant_id": bom.tenant_id, "bom_id": bom.id, **ln.model_dump()} for ln in data.lines],
    )


async def _audit(
    db: AsyncSession, bom: Bom, user_id: uuid.UUID, action: str, summary: dict[str, object]
) -> None:
    await audit.record(
        db,
        tenant_id=bom.tenant_id,
        user_id=user_id,
        action=f"catalog.bom.{action}",
        target_type="bom",
        target_id=bom.id,
        summary={"item_id": str(bom.item_id), "version": bom.version, **summary},
    )


async def create_draft(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, item_id: uuid.UUID, data: BomIn
) -> uuid.UUID:
    item = await _locked_item(db, item_id)
    qty, unit = await _validated(db, item, data)
    last = await db.scalar(select(func.max(Bom.version)).where(Bom.item_id == item_id))
    bom = Bom(
        tenant_id=tenant_id,
        item_id=item_id,
        version=(last or 0) + 1,
        yield_qty=qty,
        yield_unit_id=unit,
        status="draft",
        created_by=user_id,
    )
    db.add(bom)
    await db.flush()
    await _write_lines(db, bom, data)
    await _audit(db, bom, user_id, "create", {"after": data.model_dump(mode="json")})
    return bom.id


async def update_draft(
    db: AsyncSession, *, user_id: uuid.UUID, bom_id: uuid.UUID, data: BomIn
) -> None:
    bom = await _draft(db, bom_id)
    bom.yield_qty, bom.yield_unit_id = await _validated(
        db, await _locked_item(db, bom.item_id), data
    )
    await _write_lines(db, bom, data)
    await _audit(db, bom, user_id, "update", {"after": data.model_dump(mode="json")})


async def delete_draft(db: AsyncSession, *, user_id: uuid.UUID, bom_id: uuid.UUID) -> None:
    bom = await _draft(db, bom_id)
    await _audit(db, bom, user_id, "delete", {})
    await db.delete(bom)
    await db.flush()


async def activate(
    db: AsyncSession, *, user_id: uuid.UUID, bom_id: uuid.UUID, valid_from: date
) -> BomSummary:
    bom = await _draft(db, bom_id)
    await _locked_item(db, bom.item_id)
    latest = await db.scalar(
        select(Bom)
        .where(Bom.item_id == bom.item_id, Bom.status == "active")
        .order_by(Bom.valid_from.desc())
        .limit(1)
        .with_for_update()
    )
    if latest is not None and latest.valid_from is not None:
        if valid_from <= latest.valid_from:
            # History is not rewritten: a new version starts after the current one.
            raise ConflictError(
                "bom_start_too_early", details={"after": latest.valid_from.isoformat()}
            )
        latest.valid_to = valid_from - timedelta(days=1)
    bom.status, bom.valid_from = "active", valid_from
    await db.flush()
    await _audit(db, bom, user_id, "activate", {"valid_from": valid_from.isoformat()})
    return _summary(bom)
