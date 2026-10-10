"""Platform admin API under /admin-api (FR-ADM-001 to 003, FR-SUB-001 to 005)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service
from app.admin.models import Impersonation
from app.admin.security import AdminContext, require_admin
from app.core.errors import AppError, NotFoundError
from app.core.mailer import Email
from app.core.models import AuditLog, Membership, Outlet, Subscription, Tenant, TenantModule

router = APIRouter(prefix="/admin-api", tags=["admin"])

AnyAdmin = Annotated[AdminContext, Depends(require_admin())]
SuperAdmin = Annotated[AdminContext, Depends(require_admin("super_admin"))]
Support = Annotated[AdminContext, Depends(require_admin("super_admin", "support"))]


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="ID", pattern=r"^[A-Z]{2}$")
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")
    language: str = Field(default="id", max_length=10)
    timezone: str = Field(default="Asia/Jakarta", max_length=64)
    profile: Literal["restaurant", "cloud_kitchen", "central_kitchen_group", "hybrid"]
    owner_email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    plan_type: Literal["free", "paid"] = "free"
    ends_at: datetime | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=64)
    profile: Literal["restaurant", "cloud_kitchen", "central_kitchen_group", "hybrid"] | None = None


class SubscriptionIn(BaseModel):
    plan_type: Literal["free", "paid"]
    starts_at: datetime
    ends_at: datetime | None
    grace_days: int = Field(ge=0, le=90)
    reminders_enabled: bool
    reminder_days: list[int] = Field(max_length=10)


class ModulesIn(BaseModel):
    modules: list[str] = Field(max_length=20)


class ImpersonationIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)  # a real reason, not "x"
    minutes: int = Field(default=30, ge=5)


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    profile: str
    status: str
    subscription_state: str | None
    modules: list[str]


class Created(BaseModel):
    id: uuid.UUID


class ImpersonationOut(BaseModel):
    id: uuid.UUID
    expires_at: datetime


class ImpersonationExpired(AppError):
    status_code, code = 403, "impersonation_expired"


@asynccontextmanager
async def _tx(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as db, db.begin():
        yield db


async def _tenant_or_404(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError()
    return tenant


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(request: Request, admin: AnyAdmin) -> list[TenantOut]:
    async with _tx(request) as db:
        tenants = (await db.execute(select(Tenant).order_by(Tenant.name))).scalars().all()
        subs = {s.tenant_id: s for s in (await db.execute(select(Subscription))).scalars()}
        mods = (await db.execute(select(TenantModule).where(TenantModule.enabled))).scalars()
        by_tenant: dict[uuid.UUID, list[str]] = {}
        for m in mods:
            by_tenant.setdefault(m.tenant_id, []).append(m.module)
    return [
        TenantOut(
            id=t.id,
            name=t.name,
            profile=t.profile,
            status=t.status,
            subscription_state=subs[t.id].last_state if t.id in subs else None,
            modules=sorted(by_tenant.get(t.id, [])),
        )
        for t in tenants
    ]


@router.post("/tenants", status_code=201, response_model=Created)
async def create_tenant(body: TenantCreate, request: Request, admin: SuperAdmin) -> Created:
    settings = request.app.state.settings
    fields = body.model_dump(
        include={"name", "legal_name", "country", "currency", "language", "timezone", "profile"}
    )
    async with _tx(request) as db:
        tenant_id, token = await service.create_tenant(
            db,
            admin,
            request.app.state.permission_registry,
            fields=fields,
            owner_email=body.owner_email.strip(),
            plan_type=body.plan_type,
            ends_at=body.ends_at,
            invitation_ttl_hours=settings.invitation_ttl_hours,
        )
    link = f"{settings.app_base_url.rstrip('/')}/accept-invitation#token={token}"
    await request.app.state.mailer.send(
        Email(to=body.owner_email, subject_key="email.invitation.subject", link=link)
    )
    return Created(id=tenant_id)


@router.patch("/tenants/{tenant_id}", status_code=204)
async def update_tenant(
    tenant_id: uuid.UUID, body: TenantUpdate, request: Request, admin: SuperAdmin
) -> None:
    changes = body.model_dump(exclude_none=True)
    async with _tx(request) as db:
        tenant = await _tenant_or_404(db, tenant_id)
        for key, value in changes.items():
            setattr(tenant, key, value)
        await service.audit_admin(db, admin, tenant_id, "admin.tenant_updated", changes)


class StatusIn(BaseModel):
    # suspended: blocks all tenant access; deleted: soft delete, data kept until purge.
    status: Literal["active", "suspended", "deleted"]


@router.put("/tenants/{tenant_id}/status", status_code=204)
async def change_status(
    tenant_id: uuid.UUID, body: StatusIn, request: Request, admin: SuperAdmin
) -> None:
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        await service.set_status(db, admin, tenant_id, body.status)


@router.put("/tenants/{tenant_id}/subscription", status_code=204)
async def put_subscription(
    tenant_id: uuid.UUID, body: SubscriptionIn, request: Request, admin: SuperAdmin
) -> None:
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        await service.set_subscription(db, admin, tenant_id, body.model_dump())


@router.put("/tenants/{tenant_id}/modules", status_code=204)
async def put_modules(
    tenant_id: uuid.UUID, body: ModulesIn, request: Request, admin: SuperAdmin
) -> None:
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        await service.set_modules(db, admin, tenant_id, body.modules)


@router.post(
    "/tenants/{tenant_id}/impersonations", status_code=201, response_model=ImpersonationOut
)
async def impersonate(
    tenant_id: uuid.UUID, body: ImpersonationIn, request: Request, admin: Support
) -> ImpersonationOut:
    minutes = min(body.minutes, request.app.state.settings.impersonation_max_minutes)
    async with _tx(request) as db:
        await _tenant_or_404(db, tenant_id)
        imp = await service.start_impersonation(db, admin, tenant_id, body.reason, minutes)
    return ImpersonationOut(id=imp.id, expires_at=imp.expires_at)


@asynccontextmanager
async def _read_only_view(
    request: Request, admin: AdminContext, impersonation_id: uuid.UUID
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID]]:
    """FR-ADM-003: a READ ONLY transaction, so PostgreSQL itself rejects any write, scoped to
    the impersonated tenant, and only while the impersonation is live and owned by the caller."""
    async with request.app.state.sessionmaker() as db, db.begin():
        await db.execute(text("SET TRANSACTION READ ONLY"))
        imp = (
            await db.execute(
                select(Impersonation).where(
                    Impersonation.id == impersonation_id,
                    Impersonation.admin_id == admin.admin_id,
                )
            )
        ).scalar_one_or_none()
        if imp is None:
            raise NotFoundError()
        if imp.ended_at is not None or imp.expires_at <= datetime.now(UTC):
            raise ImpersonationExpired()
        yield db, imp.tenant_id


class ViewOutlet(BaseModel):
    id: uuid.UUID
    name: str
    type: str


class ViewAudit(BaseModel):
    at: datetime
    action: str
    actor_type: str


class ViewSummary(BaseModel):
    outlets: list[ViewOutlet]
    members: int
    recent_audit: list[ViewAudit]


@router.get("/impersonations/{impersonation_id}/summary", response_model=ViewSummary)
async def impersonation_summary(
    impersonation_id: uuid.UUID, request: Request, admin: Support
) -> ViewSummary:
    async with _read_only_view(request, admin, impersonation_id) as (db, tenant_id):
        outlets = (await db.execute(select(Outlet).where(Outlet.tenant_id == tenant_id))).scalars()
        members = (
            await db.execute(
                select(func.count())
                .select_from(Membership)
                .where(Membership.tenant_id == tenant_id)
            )
        ).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.at.desc())
                .limit(50)
            )
        ).scalars()
        return ViewSummary(
            outlets=[ViewOutlet(id=o.id, name=o.name, type=o.type) for o in outlets],
            members=members,
            recent_audit=[
                ViewAudit(at=a.at, action=a.action, actor_type=a.actor_type) for a in audit
            ],
        )


@router.post("/impersonations/{impersonation_id}/end", status_code=204)
async def end_impersonation(impersonation_id: uuid.UUID, request: Request, admin: Support) -> None:
    async with _tx(request) as db:
        imp = (
            await db.execute(
                select(Impersonation).where(
                    Impersonation.id == impersonation_id, Impersonation.admin_id == admin.admin_id
                )
            )
        ).scalar_one_or_none()
        if imp is None:
            raise NotFoundError()
        imp.ended_at = datetime.now(UTC)
        await service.audit_admin(
            db, admin, imp.tenant_id, "admin.impersonation_ended", {"impersonation_id": str(imp.id)}
        )
