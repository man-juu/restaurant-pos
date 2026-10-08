"""Recipe import (FR-IMP-001): one row per recipe line, grouped by the dish's SKU. Each dish
gets a new draft version, which the user reviews and activates (activating sets its start
date, so imported recipes never change costs or stock use by surprise). Undo deletes the
drafts that are still drafts."""

import uuid
from collections import defaultdict

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.imports.runner import Outcome
from app.modules.catalog import boms
from app.modules.catalog.models import Bom, Item, Unit
from app.modules.catalog.schemas import BomIn

COLUMNS = ("item_sku", "component_sku", "qty", "unit", "waste_pct", "yield_qty", "yield_unit")
REQUIRED = ("item_sku", "component_sku", "qty", "unit")
SAMPLE = [
    ["BIBIMBAP", "BEEF-150", "1", "pcs", "", "", ""],
    ["BIBIMBAP", "RICE", "0.2", "kg", "", "", ""],
]

Group = list[tuple[int, dict[str, str]]]


async def _maps(db: AsyncSession) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    skus = {s.lower(): i for i, s in (await db.execute(select(Item.id, Item.sku))).all()}
    units = {c.lower(): i for i, c in (await db.execute(select(Unit.id, Unit.code))).all()}
    return skus, units


def _groups(rows: list[dict[str, str]]) -> dict[str, Group]:
    out: dict[str, Group] = defaultdict(list)
    for n, row in enumerate(rows, start=2):
        out[row.get("item_sku", "").lower()].append((n, row))
    return out


def _bom_in(group: Group, skus: dict[str, uuid.UUID], units: dict[str, uuid.UUID]) -> BomIn:
    """Raises KeyError(field) for an unknown SKU or unit; ValidationError for bad numbers."""

    def ref(table: dict[str, uuid.UUID], value: str, name: str) -> uuid.UUID:
        if value.lower() not in table:
            raise KeyError(name)
        return table[value.lower()]

    first = group[0][1]
    lines = [
        {
            "component_item_id": ref(skus, r.get("component_sku", ""), "component_sku"),
            "qty": r.get("qty"),
            "unit_id": ref(units, r.get("unit", ""), "unit"),
            "waste_pct": r.get("waste_pct") or 0,
        }
        for _, r in group
    ]
    yield_unit = first.get("yield_unit")
    return BomIn.model_validate(
        {
            "yield_qty": first.get("yield_qty") or None,
            "yield_unit_id": ref(units, yield_unit, "yield_unit") if yield_unit else None,
            "lines": lines,
        }
    )


async def _one(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    group: Group,
    maps: tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]],
    out: Outcome,
) -> None:
    row_no, first = group[0]
    skus, units = maps
    try:
        item_id = skus[first.get("item_sku", "").lower()]
    except KeyError:
        out.errors.append({"row": row_no, "field": "item_sku"})
        return
    try:
        data = _bom_in(group, skus, units)
        async with db.begin_nested():  # a failed recipe never breaks the others' checks
            out.created.append(
                await boms.create_draft(
                    db, tenant_id=tenant_id, user_id=user_id, item_id=item_id, data=data
                )
            )
    except KeyError as exc:
        out.errors.append({"row": row_no, "field": str(exc.args[0])})
    except ValidationError as exc:
        out.errors.extend({"row": row_no, "field": str(e["loc"][-1])} for e in exc.errors())
    except AppError as exc:
        out.errors.append({"row": row_no, "field": exc.code})


def builder(tenant_id: uuid.UUID, user_id: uuid.UUID):  # type: ignore[no-untyped-def]
    async def build(db: AsyncSession, rows: list[dict[str, str]]) -> Outcome:
        out, maps = Outcome(), await _maps(db)
        for group in _groups(rows).values():
            await _one(db, tenant_id, user_id, group, maps, out)
        return out

    return build


async def undo(db: AsyncSession, user_id: uuid.UUID, bom_ids: list[uuid.UUID]) -> int:
    drafts = await db.scalars(select(Bom.id).where(Bom.id.in_(bom_ids), Bom.status == "draft"))
    removed = 0
    for bom_id in list(drafts):
        await boms.delete_draft(db, user_id=user_id, bom_id=bom_id)
        removed += 1
    return removed
