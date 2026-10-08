"""Import and export endpoints for items (FR-IMP-001 to 003). Files go as the raw request body
with `file_name` in the query (the extension picks CSV or XLSX)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.access.policy import Principal, require
from app.core.imports.models import ImportBatch
from app.core.tabular import write_csv, write_xlsx
from app.core.tenancy import tenant_session
from app.core.uploads.service import read_body
from app.modules.catalog import item_import
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Item, ItemCategory, ItemTranslation, Unit

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Create = Annotated[Principal, Depends(require(perm.ITEM_CREATE))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]
FileName = Annotated[str, Query(min_length=1, max_length=200, pattern=r"^[^/\\]+\.(csv|xlsx)$")]
Format = Literal["csv", "xlsx"]
MAX_FILE = 5 * 1024 * 1024
TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ImportCheckOut(BaseModel):
    rows_ok: int
    errors: list[dict[str, Any]]


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    kind: str
    file_name: str
    status: str
    row_count: int
    created_at: datetime
    reverted_at: datetime | None


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _file(data: bytes, fmt: Format, name: str) -> Response:
    return Response(
        data,
        media_type=TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'},
    )


def _table(fmt: Format, header: tuple[str, ...], rows: list[list[Any]]) -> bytes:
    return write_xlsx(header, rows) if fmt == "xlsx" else write_csv(header, rows)


@router.get("/imports", response_model=list[ImportBatchOut])
async def list_imports(request: Request, p: Create) -> list[ImportBatchOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(
            select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(50)
        )
        return [ImportBatchOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/imports/items/template")
async def item_template(p: Create, format: Format = "xlsx") -> Response:
    return _file(_table(format, item_import.COLUMNS, item_import.SAMPLE), format, "items-template")


@router.post("/imports/items/check", response_model=ImportCheckOut)
async def check_items(request: Request, p: Create, file_name: FileName) -> ImportCheckOut:
    raw = await read_body(request, MAX_FILE)
    async with _db(request, p) as db:
        checked = await item_import.check(db, raw, file_name)
    return ImportCheckOut(rows_ok=len(checked.items), errors=checked.errors[:200])


@router.post("/imports/items", response_model=ImportBatchOut, status_code=201)
async def import_items(request: Request, p: Create, file_name: FileName) -> ImportBatchOut:
    raw = await read_body(request, MAX_FILE)
    async with _db(request, p) as db:
        batch = await item_import.commit(
            db, tenant_id=p.tenant_id, user_id=p.user_id, raw=raw, file_name=file_name
        )
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.post("/imports/{batch_id}/revert", response_model=ImportBatchOut)
async def revert_import(batch_id: uuid.UUID, request: Request, p: Update) -> ImportBatchOut:
    async with _db(request, p) as db:
        batch = await item_import.revert(
            db, tenant_id=p.tenant_id, user_id=p.user_id, batch_id=batch_id
        )
        await db.flush()
        await db.refresh(batch)
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.get("/exports/items")  # not /items/export: /items/{item_id} would catch it
async def export_items(request: Request, p: View, format: Format = "xlsx") -> Response:
    """Same columns as the import template, so an export can be edited and imported elsewhere."""
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
        ]
        for i, n_en, n_id, unit, cat in result
    ]
    return _file(_table(format, item_import.COLUMNS, rows), format, "items")
