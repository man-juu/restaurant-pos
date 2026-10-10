"""Tenant data export and restore requests from the platform admin (FR-ADM-007). The admin
can start an export for a tenant (the owner downloads it in the app) and record a restore
request for the runbook; neither shows tenant data to the admin."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.admin import service
from app.admin.models import RestoreRequest
from app.admin.router import _tenant_or_404, _tx
from app.admin.security import AdminContext, require_admin
from app.core.errors import ConflictError
from app.core.exports.models import DataExport

router = APIRouter(prefix="/admin-api/tenants", tags=["admin"])
SuperAdmin = Annotated[AdminContext, Depends(require_admin("super_admin"))]
Support = Annotated[AdminContext, Depends(require_admin("super_admin", "support"))]


class ExportRow(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    finished_at: datetime | None


class RestoreIn(BaseModel):
    restore_to: datetime
    reason: str = Field(min_length=10, max_length=500)


class RestoreRow(BaseModel):
    id: uuid.UUID
    restore_to: datetime
    reason: str
    status: str
    requested_at: datetime


@router.get("/{tenant_id}/exports", response_model=list[ExportRow])
async def list_exports(tenant_id: uuid.UUID, request: Request, admin: Support) -> list[ExportRow]:
    async with _tx(request) as db:
        rows = await db.scalars(
            select(DataExport)
            .where(DataExport.tenant_id == tenant_id)
            .order_by(DataExport.created_at.desc())
            .limit(20)
        )
        return [
            ExportRow(id=r.id, status=r.status, created_at=r.created_at, finished_at=r.finished_at)
            for r in rows
        ]


@router.post("/{tenant_id}/exports", response_model=ExportRow, status_code=202)
async def start_export(tenant_id: uuid.UUID, request: Request, admin: SuperAdmin) -> ExportRow:
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        waiting = await db.scalar(
            select(DataExport.id).where(
                DataExport.tenant_id == tenant_id, DataExport.status == "queued"
            )
        )
        if waiting:
            raise ConflictError("export_already_queued")
        row = DataExport(tenant_id=tenant_id, requested_by_admin=admin.admin_id, status="queued")
        db.add(row)
        await db.flush()
        await service.audit_admin(db, admin, tenant_id, "admin.tenant.export", {})
        return ExportRow(id=row.id, status=row.status, created_at=row.created_at, finished_at=None)


@router.get("/{tenant_id}/restore-requests", response_model=list[RestoreRow])
async def list_restores(tenant_id: uuid.UUID, request: Request, admin: Support) -> list[RestoreRow]:
    async with _tx(request) as db:
        rows = await db.scalars(
            select(RestoreRequest)
            .where(RestoreRequest.tenant_id == tenant_id)
            .order_by(RestoreRequest.requested_at.desc())
        )
        return [RestoreRow.model_validate(r, from_attributes=True) for r in rows]


@router.post("/{tenant_id}/restore-requests", response_model=RestoreRow, status_code=201)
async def request_restore(
    tenant_id: uuid.UUID, body: RestoreIn, request: Request, admin: SuperAdmin
) -> RestoreRow:
    if body.restore_to >= datetime.now(UTC):
        raise ConflictError("restore_point_in_future")
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        row = RestoreRequest(
            tenant_id=tenant_id,
            restore_to=body.restore_to,
            reason=body.reason,
            requested_by=admin.admin_id,
        )
        db.add(row)
        await db.flush()
        await service.audit_admin(
            db,
            admin,
            tenant_id,
            "admin.tenant.restore_request",
            {"restore_to": str(body.restore_to)},
        )
        return RestoreRow.model_validate(row, from_attributes=True)
