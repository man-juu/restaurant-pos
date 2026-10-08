"""Import and export endpoints for items (FR-IMP-001 to 003). Files go as the raw request body
with `file_name` in the query (the extension picks CSV or XLSX)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.access.policy import Principal, require
from app.core.imports import runner
from app.core.imports.http import (
    MAX_FILE,
    FileName,
    Format,
    ImportBatchOut,
    ImportCheckOut,
    table_file,
)
from app.core.imports.models import ImportBatch
from app.core.tenancy import tenant_session
from app.core.uploads.service import read_body
from app.modules.catalog import item_import, recipe_import
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Item, ItemCategory, ItemTranslation, Unit

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Create = Annotated[Principal, Depends(require(perm.ITEM_CREATE))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/imports", response_model=list[ImportBatchOut])
async def list_imports(request: Request, p: Create) -> list[ImportBatchOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(
            select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(50)
        )
        return [ImportBatchOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/imports/items/template")
async def item_template(p: Create, format: Format = "xlsx") -> Response:
    return table_file(format, "items-template", item_import.COLUMNS, item_import.SAMPLE)


@router.post("/imports/items/check", response_model=ImportCheckOut)
async def check_items(
    request: Request, p: Create, file_name: FileName, create_categories: bool = True
) -> ImportCheckOut:
    raw = await read_body(request, MAX_FILE)
    async with _db(request, p) as db:
        checked = await item_import.check(db, raw, file_name, create_categories)
    return ImportCheckOut(
        rows_ok=len(checked.items),
        errors=checked.errors[:200],
        new_categories=checked.new_categories[:200],
    )


@router.post("/imports/items", response_model=ImportBatchOut, status_code=201)
async def import_items(
    request: Request, p: Create, file_name: FileName, create_categories: bool = True
) -> ImportBatchOut:
    raw = await read_body(request, MAX_FILE)
    async with _db(request, p) as db:
        batch = await item_import.commit(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            raw=raw,
            file_name=file_name,
            create_categories=create_categories,
        )
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.post("/imports/{batch_id}/revert", response_model=ImportBatchOut)
async def revert_import(batch_id: uuid.UUID, request: Request, p: Update) -> ImportBatchOut:
    async with _db(request, p) as db:
        batch = await item_import.revert(db, user_id=p.user_id, batch_id=batch_id)
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.get("/imports/recipes/template")
async def recipe_template(p: Create, format: Format = "xlsx") -> Response:
    return table_file(format, "recipes-template", recipe_import.COLUMNS, recipe_import.SAMPLE)


@router.post("/imports/recipes/check", response_model=ImportCheckOut)
async def check_recipes(request: Request, p: Create, file_name: FileName) -> ImportCheckOut:
    raw = await read_body(request, MAX_FILE)
    rows = runner.rows_of(raw, file_name, recipe_import.REQUIRED)
    async with _db(request, p) as db:
        out = await runner.check(db, rows, recipe_import.builder(p.tenant_id, p.user_id))
    return ImportCheckOut(rows_ok=len(rows) if not out.errors else 0, errors=out.errors[:200])


@router.post("/imports/recipes", response_model=ImportBatchOut, status_code=201)
async def import_recipes(request: Request, p: Create, file_name: FileName) -> ImportBatchOut:
    """Creates one draft version per dish; activate each after review."""
    raw = await read_body(request, MAX_FILE)
    rows = runner.rows_of(raw, file_name, recipe_import.REQUIRED)
    async with _db(request, p) as db:
        batch = await runner.commit(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            kind="recipes",
            raw=raw,
            file_name=file_name,
            rows=rows,
            build=recipe_import.builder(p.tenant_id, p.user_id),
        )
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.get("/exports/items")  # not /items/export: /items/{item_id} would catch it
async def export_items(request: Request, p: View, format: Format = "xlsx") -> Response:
    """Same columns as the import template, so an export can be edited and imported elsewhere.
    Standard costs only for users who may see costs (docs/03 rule 5)."""
    show_cost = p.can(perm.COST_VIEW)
    en, id_ = aliased(ItemTranslation), aliased(ItemTranslation)
    stmt = (
        select(Item, en.name, id_.name, Unit.code, ItemCategory.name)
        .join(Unit, Unit.id == Item.base_unit_id)
        .outerjoin(ItemCategory, ItemCategory.id == Item.category_id)
        .outerjoin(en, (en.item_id == Item.id) & (en.language == "en"))
        .outerjoin(id_, (id_.item_id == Item.id) & (id_.language == "id"))
        .where(Item.is_active)
        .order_by(Item.sku)
        .limit(50_000)
    )
    async with _db(request, p) as db:
        result = (await db.execute(stmt)).all()
    rows = [
        [
            i.sku,
            i.type,
            n_en or "",
            n_id or "",
            unit,
            cat or "",
            i.storage_type or "",
            i.shelf_life_days or "",
            "yes" if i.is_stocked else "no",
            i.tracking_mode,
            i.standard_cost if show_cost and i.standard_cost is not None else "",
        ]
        for i, n_en, n_id, unit, cat in result
    ]
    return table_file(format, "items", item_import.COLUMNS, rows)
