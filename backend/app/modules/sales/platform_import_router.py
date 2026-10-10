"""FR-IMP-004 endpoints: the saved column mapping per platform channel, then check, import
and undo a sales export file. Needs `sales.day.enter` and access to the outlet."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.imports import runner
from app.core.imports.http import MAX_FILE, FileName, ImportBatchOut
from app.core.tabular import read_table
from app.core.tenancy import tenant_session
from app.core.uploads.service import read_body
from app.modules.catalog.interface import channel_code
from app.modules.sales import permissions as perm
from app.modules.sales import platform_import, service
from app.modules.sales.models import SalesDocument
from app.modules.sales.platform_import_models import PlatformImportMapping

router = APIRouter(prefix="/api/v1/sales/platform-imports", tags=["sales"])
Enter = Annotated[Principal, Depends(require(perm.DAY_ENTER))]
Column = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100)
]


class ColumnMapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_column: Column
    code_column: Column
    qty_column: Column
    amount_column: Column | None = None  # what the platform charged for the row
    date_format: Literal["ymd", "dmy", "mdy"] = "dmy"


class ColumnMapOut(ColumnMapIn):
    channel_id: uuid.UUID


class DayTotalOut(BaseModel):
    business_date: date
    total: int
    replaces: bool  # an entry for this day and channel exists and will be replaced


class PlatformCheckOut(BaseModel):
    rows_ok: int
    errors: list[dict[str, object]]
    days: list[DayTotalOut]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


async def _mapping(db: AsyncSession, channel_id: uuid.UUID) -> PlatformImportMapping:
    m = await db.scalar(
        select(PlatformImportMapping).where(PlatformImportMapping.channel_id == channel_id)
    )
    if m is None:
        raise NotFoundError("mapping_not_found")
    return m


@router.get("/mappings/{channel_id}", response_model=ColumnMapOut)
async def get_mapping(channel_id: uuid.UUID, request: Request, p: Enter) -> ColumnMapOut:
    async with _db(request, p) as db:
        return ColumnMapOut.model_validate(await _mapping(db, channel_id), from_attributes=True)


@router.put("/mappings/{channel_id}", response_model=ColumnMapOut)
async def save_mapping(
    channel_id: uuid.UUID, body: ColumnMapIn, request: Request, p: Enter
) -> ColumnMapOut:
    async with _db(request, p) as db:
        await channel_code(db, channel_id)  # unknown channel: 404
        try:
            m = await _mapping(db, channel_id)
        except NotFoundError:
            m = PlatformImportMapping(tenant_id=p.tenant_id, channel_id=channel_id)
            db.add(m)
        for field, value in body.model_dump().items():
            setattr(m, field, value)
        m.updated_by = p.user_id
        await db.flush()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="sales.platform_mapping.save",
            target_type="channel",
            target_id=channel_id,
            summary=body.model_dump(),
        )
        return ColumnMapOut(channel_id=channel_id, **body.model_dump())


@router.post("/columns", response_model=list[str])
async def file_columns(request: Request, p: Enter, file_name: FileName) -> list[str]:
    """The file's header, so the mapping can be picked from real column names."""
    rows = read_table(await read_body(request, MAX_FILE), file_name)
    return list(rows[0].keys()) if rows else []


async def _days(db: AsyncSession, outlet_id: uuid.UUID, m: PlatformImportMapping, rows):  # type: ignore[no-untyped-def]
    out = runner.Outcome()
    lookup = await platform_import.lookup(db, m, rows)
    days = platform_import.group(rows, m, lookup, out)
    live = set(
        await db.scalars(
            select(SalesDocument.business_date).where(
                SalesDocument.outlet_id == outlet_id,
                SalesDocument.channel_id == m.channel_id,
                SalesDocument.business_date.in_(days.keys()),
                SalesDocument.source == "manual_day",
                SalesDocument.status == "posted",
            )
        )
    )
    return [
        DayTotalOut(
            business_date=d, total=sum(int(a) for _, a in lines.values()), replaces=d in live
        )
        for d, lines in sorted(days.items())
    ]


@router.post("/check", response_model=PlatformCheckOut)
async def check_import(
    request: Request, p: Enter, file_name: FileName, outlet_id: uuid.UUID, channel_id: uuid.UUID
) -> PlatformCheckOut:
    p.require_outlet(outlet_id)
    rows = read_table(await read_body(request, MAX_FILE), file_name)
    async with _db(request, p) as db:
        m = await _mapping(db, channel_id)
        build = platform_import.builder(p.user_id, p.tenant_id, outlet_id, m)
        out = await runner.check(db, rows, build)
        days = await _days(db, outlet_id, m, rows)
    return PlatformCheckOut(
        rows_ok=0 if out.errors else len(rows), errors=out.errors[:200], days=days
    )


@router.post("", response_model=ImportBatchOut, status_code=201)
async def run_import(
    request: Request, p: Enter, file_name: FileName, outlet_id: uuid.UUID, channel_id: uuid.UUID
) -> ImportBatchOut:
    p.require_outlet(outlet_id)
    raw = await read_body(request, MAX_FILE)
    rows = read_table(raw, file_name)
    async with _db(request, p) as db:
        m = await _mapping(db, channel_id)
        batch = await runner.commit(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            kind="platform_sales",
            raw=raw,
            file_name=file_name,
            rows=rows,
            build=platform_import.builder(p.user_id, p.tenant_id, outlet_id, m),
        )
        return ImportBatchOut.model_validate(batch, from_attributes=True)


@router.post("/{batch_id}/revert", response_model=ImportBatchOut)
async def revert_import(batch_id: uuid.UUID, request: Request, p: Enter) -> ImportBatchOut:
    """Withdraws each day entry the file made (stock comes back); days replaced since stay."""
    async with _db(request, p) as db:
        batch = await runner.open_for_revert(db, batch_id, {"platform_sales"})
        undone = 0
        for doc_id in (uuid.UUID(i) for i in batch.created_ids):
            doc = await db.get(SalesDocument, doc_id)
            if doc is not None:
                p.require_outlet(doc.outlet_id)
                undone += await service.undo_entry(db, doc_id, p.user_id)
        batch = await runner.mark_reverted(db, batch, user_id=p.user_id, summary={"undone": undone})
        return ImportBatchOut.model_validate(batch, from_attributes=True)
