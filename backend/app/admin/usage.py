"""Platform console: usage per tenant (FR-ADM-004) and feature flags (FR-ADM-006).
Reads go through the admin role's explicit policies; flag changes are audited to the tenant."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.models import JobFailure
from app.admin.security import AdminContext, require_admin
from app.core.errors import AppError, NotFoundError
from app.core.flags import FLAGS, TenantFlag
from app.core.models import AuditLog, Membership, Outlet, Tenant
from app.core.uploads.models import Upload

router = APIRouter(prefix="/admin-api/tenants", tags=["admin"])
AnyAdmin = Annotated[AdminContext, Depends(require_admin())]
SuperAdmin = Annotated[AdminContext, Depends(require_admin("super_admin"))]
FAILURE_DAYS = 7


class UnknownFlag(AppError):
    status_code, code = 422, "unknown_flag"


class Usage(BaseModel):
    outlets: int
    active_users: int
    last_activity: datetime | None
    storage_bytes: int
    job_failures_7d: int
    flags: dict[str, bool]


class FlagsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flags: dict[str, bool] = Field(max_length=50)


async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await db.get(Tenant, tenant_id) is None:
        raise NotFoundError()


async def _flags(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, bool]:
    rows = dict(
        (
            await db.execute(
                select(TenantFlag.flag, TenantFlag.enabled).where(TenantFlag.tenant_id == tenant_id)
            )
        ).all()
    )
    return {name: rows.get(name, default) for name, (default, _) in FLAGS.items()}


async def _count(db: AsyncSession, stmt: object) -> int:
    return int(await db.scalar(stmt) or 0)  # type: ignore[call-overload]


@router.get("/{tenant_id}/usage", response_model=Usage)
async def usage(tenant_id: uuid.UUID, request: Request, admin: AnyAdmin) -> Usage:
    since = datetime.now(UTC) - timedelta(days=FAILURE_DAYS)
    async with request.app.state.sessionmaker() as db, db.begin():
        await _tenant(db, tenant_id)
        return Usage(
            outlets=await _count(
                db, select(func.count()).select_from(Outlet).where(Outlet.tenant_id == tenant_id)
            ),
            active_users=await _count(
                db,
                select(func.count())
                .select_from(Membership)
                .where(Membership.tenant_id == tenant_id, Membership.status == "active"),
            ),
            last_activity=await db.scalar(
                select(func.max(AuditLog.at)).where(AuditLog.tenant_id == tenant_id)
            ),
            storage_bytes=await _count(
                db,
                select(func.coalesce(func.sum(Upload.byte_size), 0)).where(
                    Upload.tenant_id == tenant_id
                ),
            ),
            job_failures_7d=await _count(
                db,
                select(func.count())
                .select_from(JobFailure)
                .where(JobFailure.tenant_id == tenant_id, JobFailure.at >= since),
            ),
            flags=await _flags(db, tenant_id),
        )


@router.put("/{tenant_id}/flags", response_model=dict[str, bool])
async def set_flags(
    tenant_id: uuid.UUID, body: FlagsIn, request: Request, admin: SuperAdmin
) -> dict[str, bool]:
    if unknown := set(body.flags) - FLAGS.keys():
        raise UnknownFlag(details={"flags": sorted(unknown)})
    async with request.app.state.sessionmaker() as db, db.begin():
        await _tenant(db, tenant_id)
        for name, enabled in body.flags.items():
            stmt = insert(TenantFlag).values(tenant_id=tenant_id, flag=name, enabled=enabled)
            await db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["tenant_id", "flag"],
                    set_={"enabled": enabled, "updated_at": func.now()},
                )
            )
        await service.audit_admin(db, admin, tenant_id, "admin.flags.set", {"flags": body.flags})
        return await _flags(db, tenant_id)
