"""Tenant data export (FR-TEN-010) for those with tenant.data.export (owner by default)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.exports import service
from app.core.exports.models import DataExport
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/tenant/exports", tags=["tenant"])
Export = Annotated[Principal, Depends(require("tenant.data.export"))]


class ExportOut(BaseModel):
    id: uuid.UUID
    status: str
    byte_size: int | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    by_admin: bool


def _out(r: DataExport) -> ExportOut:
    return ExportOut(
        id=r.id,
        status=r.status,
        byte_size=r.byte_size,
        created_at=r.created_at,
        finished_at=r.finished_at,
        expires_at=r.expires_at,
        by_admin=r.requested_by_admin is not None,
    )


def _live_key(row: DataExport | None) -> str:
    """The file of a ready export that has not expired; anything else is "not found"."""
    if row is None or row.status != "ready" or not row.file_key or not row.expires_at:
        raise NotFoundError("export_not_found")
    if row.expires_at <= datetime.now(UTC):
        raise NotFoundError("export_not_found")
    return row.file_key


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[ExportOut])
async def list_exports(request: Request, p: Export) -> list[ExportOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(select(DataExport).order_by(DataExport.created_at.desc()).limit(20))
        return [_out(r) for r in rows]


@router.post("", response_model=ExportOut, status_code=202)
async def request_export(request: Request, p: Export) -> ExportOut:
    """Queued; the worker builds it within about ten minutes."""
    async with _db(request, p) as db:
        row = await service.request_export(db, tenant_id=p.tenant_id, user_id=p.user_id)
        return _out(row)


@router.get("/{export_id}/download", response_class=FileResponse)
async def download(export_id: uuid.UUID, request: Request, p: Export) -> FileResponse:
    settings = request.app.state.settings
    async with _db(request, p) as db:
        row = await db.get(DataExport, export_id)
        key = _live_key(row)
        path = service.export_path(settings, key)
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="tenant.export.download",
            target_type="data_export",
            target_id=export_id,
            summary={},
        )
    if not path.is_file():
        raise NotFoundError("export_not_found")
    return FileResponse(
        path,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="export-{export_id}.zip"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
