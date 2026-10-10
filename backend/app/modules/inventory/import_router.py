"""Opening stock import (FR-IMP-001, 002). Needs `inventory.opening.post`; rows for outlets the
user cannot access are refused like unknown outlets."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

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
from app.core.tenancy import tenant_session
from app.core.uploads.service import read_body
from app.modules.catalog.interface import tenant_today
from app.modules.inventory import opening_import
from app.modules.inventory import permissions as perm

router = APIRouter(prefix="/api/v1/inventory/imports", tags=["inventory"])

Post = Annotated[Principal, Depends(require(perm.OPENING_POST))]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/opening/template")
async def opening_template(p: Post, format: Format = "xlsx") -> Response:
    return table_file(
        format, "opening-stock-template", opening_import.COLUMNS, opening_import.SAMPLE
    )


async def _rows(request: Request, file_name: str) -> tuple[bytes, list[dict[str, str]]]:
    raw = await read_body(request, MAX_FILE)
    return raw, runner.rows_of(raw, file_name, opening_import.REQUIRED)


@router.post("/opening/check", response_model=ImportCheckOut)
async def check_opening(
    request: Request, p: Post, file_name: FileName, business_date: date | None = None
) -> ImportCheckOut:
    _, rows = await _rows(request, file_name)
    async with _db(request, p) as db:
        day = business_date or await tenant_today(db, p.tenant_id)
        out = await runner.check(db, rows, opening_import.builder(p, day))
    return ImportCheckOut(rows_ok=0 if out.errors else len(rows), errors=out.errors[:200])


@router.post("/opening", response_model=ImportBatchOut, status_code=201)
async def import_opening(
    request: Request, p: Post, file_name: FileName, business_date: date | None = None
) -> ImportBatchOut:
    raw, rows = await _rows(request, file_name)
    async with _db(request, p) as db:
        day = business_date or await tenant_today(db, p.tenant_id)
        batch = await runner.commit(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            kind="opening_stock",
            raw=raw,
            file_name=file_name,
            rows=rows,
            build=opening_import.builder(p, day),
        )
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.post("/{batch_id}/revert", response_model=ImportBatchOut)
async def revert_opening(batch_id: uuid.UUID, request: Request, p: Post) -> ImportBatchOut:
    """Posts reversals for every opening document the import created."""
    async with _db(request, p) as db:
        batch = await runner.open_for_revert(db, batch_id, {"opening_stock"})
        ids = [uuid.UUID(i) for i in batch.created_ids]
        done = await opening_import.undo(db, p, ids)
        batch = await runner.mark_reverted(db, batch, user_id=p.user_id, summary={"reversed": done})
        return ImportBatchOut.model_validate(batch, from_attributes=True)
