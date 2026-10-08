"""Item import from CSV/XLSX (FR-IMP-001, 002): check every row first, then create all items
in one transaction or none. Re-importing the same file is refused (file hash); an import can
be undone, which archives the items it created (master data is never deleted)."""

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError
from app.core.imports import runner
from app.core.imports.models import ImportBatch
from app.core.tabular import InvalidTable, read_table
from app.modules.catalog import recipe_import, service
from app.modules.catalog.models import Item, ItemCategory, Unit
from app.modules.catalog.schemas import CategoryIn, ItemIn

COLUMNS = (
    "sku",
    "type",
    "name_en",
    "name_id",
    "base_unit",
    "category",
    "storage_type",
    "shelf_life_days",
    "is_stocked",
    "tracking_mode",
    "standard_cost",
)
REQUIRED = ("sku", "type", "base_unit")
TRACKING_ALIASES = {"tepat": "exact", "perkiraan": "estimated", "tidak": "untracked"}
TYPE_ALIASES = {
    "bahan": "ingredient",
    "setengah_jadi": "semi_finished",
    "semi-finished": "semi_finished",
}
TRUE, FALSE = {"", "1", "yes", "ya", "true", "y"}, {"0", "no", "tidak", "false", "n"}
SAMPLE = [
    [
        "BEEF-150",
        "ingredient",
        "Beef bulgogi pack 150 g",
        "Daging bulgogi 150 g",
        "pcs",
        "",
        "frozen",
        "90",
        "yes",
    ],
    ["RICE", "ingredient", "Rice", "Beras", "kg", "", "dry", "", "yes"],
    ["BIBIMBAP", "menu", "Bibimbap", "Bibimbap", "pcs", "", "", "", "no"],
]


@dataclass
class Checked:
    items: list[ItemIn] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    # Category name per item (same order as `items`) when it does not exist yet.
    pending: list[str | None] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Lookups:
    units: dict[str, uuid.UUID]
    categories: dict[str, uuid.UUID]
    skus: set[str]
    create_categories: bool = True


async def _lookups(db: AsyncSession, create_categories: bool) -> Lookups:
    units = {
        code.lower(): uid for uid, code in (await db.execute(select(Unit.id, Unit.code))).all()
    }
    cats = {
        name.lower(): cid
        for cid, name in (await db.execute(select(ItemCategory.id, ItemCategory.name))).all()
    }
    skus = {s.lower() for s in (await db.scalars(select(Item.sku)))}
    return Lookups(units, cats, skus, create_categories)


def _tracking(value: str) -> str | None:
    v = value.lower()
    return TRACKING_ALIASES.get(v, v) or None


def _flag(value: str) -> bool | None:
    v = value.lower()
    return True if v in TRUE else False if v in FALSE else None


def _row_to_item(row: dict[str, str], look: Lookups) -> tuple[dict[str, Any], list[str]]:
    problems = [f for f in REQUIRED if not row.get(f)]
    unit = look.units.get(row.get("base_unit", "").lower())
    if row.get("base_unit") and unit is None:
        problems.append("base_unit")
    category = look.categories.get(row.get("category", "").lower()) if row.get("category") else None
    if row.get("category") and category is None and not look.create_categories:
        problems.append("category")
    stocked = _flag(row.get("is_stocked", ""))
    if stocked is None:
        problems.append("is_stocked")
    names = [(lang, row.get(f"name_{lang}", "")) for lang in ("en", "id")]
    data = {
        "sku": row.get("sku", ""),
        "type": TYPE_ALIASES.get(row.get("type", "").lower(), row.get("type", "").lower()),
        "base_unit_id": unit,
        "category_id": category,
        "storage_type": row.get("storage_type", "").lower() or None,
        "shelf_life_days": row.get("shelf_life_days") or None,
        "is_stocked": bool(stocked),
        "tracking_mode": _tracking(row.get("tracking_mode", "")),
        "standard_cost": row.get("standard_cost") or None,
        "translations": [{"language": lang, "name": n} for lang, n in names if n],
    }
    return data, problems


def _check_row(n: int, row: dict[str, str], look: Lookups, seen: set[str], out: Checked) -> None:
    data, problems = _row_to_item(row, look)
    sku = data["sku"].lower()
    if sku in look.skus or sku in seen:
        problems.append("sku_taken")
    seen.add(sku)
    if problems:
        out.errors.extend({"row": n, "field": p} for p in problems)
        return
    try:
        out.items.append(ItemIn.model_validate(data))
    except ValidationError as exc:
        out.errors.extend({"row": n, "field": str(e["loc"][0])} for e in exc.errors())
        return
    name = row.get("category", "")
    missing = bool(name) and data["category_id"] is None
    if missing and len(name) > 120:
        out.items.pop()
        out.errors.append({"row": n, "field": "category"})
        return
    out.pending.append(name if missing else None)
    if missing and name.lower() not in {c.lower() for c in out.new_categories}:
        out.new_categories.append(name)


async def check(
    db: AsyncSession, raw: bytes, file_name: str, create_categories: bool = True
) -> Checked:
    rows = read_table(raw, file_name)
    missing = [c for c in REQUIRED if rows and c not in rows[0]]
    if missing:
        raise InvalidTable("missing_columns", details={"columns": missing})
    look, out, seen = await _lookups(db, create_categories), Checked(), set[str]()
    for n, row in enumerate(rows, start=2):  # row 1 is the header in the user's sheet
        _check_row(n, row, look, seen, out)
    return out


async def _create_categories(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, names: list[str]
) -> dict[str, uuid.UUID]:
    made = {}
    for name in names:
        row = await service.save_category(
            db, tenant_id=tenant_id, user_id=user_id, data=CategoryIn(name=name)
        )
        made[name.lower()] = row.id
    return made


async def commit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    raw: bytes,
    file_name: str,
    create_categories: bool = True,
) -> ImportBatch:
    digest = hashlib.sha256(raw).hexdigest()
    done = await db.scalar(
        select(ImportBatch).where(ImportBatch.kind == "items", ImportBatch.file_sha256 == digest)
    )
    if done is not None:
        raise ConflictError("already_imported", details={"batch_id": str(done.id)})
    checked = await check(db, raw, file_name, create_categories)
    if checked.errors:
        raise InvalidTable("rows_invalid", details={"errors": checked.errors[:200]})
    made = await _create_categories(db, tenant_id, user_id, checked.new_categories)
    for item, name in zip(checked.items, checked.pending, strict=True):
        if name:
            item.category_id = made[name.lower()]
    ids = [
        await service.create_item(db, tenant_id=tenant_id, user_id=user_id, data=item)
        for item in checked.items
    ]
    batch = ImportBatch(
        tenant_id=tenant_id,
        kind="items",
        file_sha256=digest,
        file_name=file_name[:200],
        row_count=len(ids),
        created_ids=[str(i) for i in ids],
        created_by=user_id,
    )
    db.add(batch)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.import.commit",
        target_type="import_batch",
        target_id=batch.id,
        summary={"kind": "items", "rows": len(ids), "file": file_name[:200]},
    )
    return batch


async def revert(db: AsyncSession, *, user_id: uuid.UUID, batch_id: uuid.UUID) -> ImportBatch:
    """Items: archive what the import created. Recipes: delete drafts still unused."""
    batch = await runner.open_for_revert(db, batch_id, {"items", "recipes"})
    ids = [uuid.UUID(i) for i in batch.created_ids]
    if batch.kind == "recipes":
        removed = await recipe_import.undo(db, user_id, ids)
        return await runner.mark_reverted(
            db, batch, user_id=user_id, summary={"deleted_drafts": removed}
        )
    await db.execute(update(Item).where(Item.id.in_(ids)).values(is_active=False))
    return await runner.mark_reverted(
        db, batch, user_id=user_id, summary={"archived_items": len(ids)}
    )
