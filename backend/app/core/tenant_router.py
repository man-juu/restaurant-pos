"""Tenant-level endpoints: outlets and the caller's capabilities (FR-TEN-002, FR-IDN-010)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access.permissions import Registry
from app.core.access.policy import Principal, require, require_member
from app.core.access.subscription import days_left
from app.core.errors import NotFoundError
from app.core.flags import overrides_subquery, resolve
from app.core.models import Outlet, Role, Tenant
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1", tags=["tenant"])


class OutletOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    timezone: str
    is_active: bool


class SubscriptionBanner(BaseModel):
    state: str
    days_left: int | None


class Capabilities(BaseModel):
    tenant_id: uuid.UUID
    permissions: list[str]
    all_outlets: bool
    outlet_ids: list[uuid.UUID]
    modules: list[str]
    subscription: SubscriptionBanner
    nav: list[str]
    flags: list[str] = []  # FR-ADM-006: feature flags on for this tenant
    # Formatting defaults for the UI (FR-X-002): money in this currency's minor units, and
    # names fall back to the tenant's default language.
    currency: str
    language: str


@router.get("/outlets", response_model=list[OutletOut])
async def list_outlets(
    request: Request, p: Annotated[Principal, Depends(require("tenant.outlet.view"))]
) -> list[OutletOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        stmt = select(Outlet).order_by(Outlet.name)
        if not p.all_outlets:  # outlet scope (docs/03)
            stmt = stmt.where(Outlet.id.in_(p.outlet_ids))
        rows = (await db.execute(stmt)).scalars()
        return [OutletOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/outlets/{outlet_id}", response_model=OutletOut)
async def get_outlet(
    outlet_id: uuid.UUID,
    request: Request,
    p: Annotated[Principal, Depends(require("tenant.outlet.view"))],
) -> OutletOut:
    """Another tenant's outlet is invisible (RLS); one outside the caller's scope is 404 too."""
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        row = (await db.execute(select(Outlet).where(Outlet.id == outlet_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError()
    return OutletOut.model_validate(row, from_attributes=True)


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    template_key: str | None


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    request: Request, p: Annotated[Principal, Depends(require("tenant.settings.view"))]
) -> list[RoleOut]:
    """The tenant's own roles (templates with tenant_id NULL are excluded)."""
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rows = (
            await db.execute(select(Role).where(Role.tenant_id.is_not(None)).order_by(Role.name))
        ).scalars()
        return [RoleOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/me/capabilities", response_model=Capabilities)
async def capabilities(
    request: Request, p: Annotated[Principal, Depends(require_member())]
) -> Capabilities:
    """What the UI may show. Convenience only: every route re-checks on the server."""
    registry: Registry = request.app.state.permission_registry
    nav = [
        key
        for m in request.app.state.modules
        if m.name in p.enabled_modules and any(p.can(c) for c in m.permissions)
        for key in m.nav
        if key not in m.nav_permissions or p.can(m.nav_permissions[key])
    ]
    # A switched-off module's permissions stay in the role but are not offered in the UI.
    switched_off = {
        c
        for m in request.app.state.modules
        if m.name not in p.enabled_modules
        for c in m.permissions
    }
    owners = p.can("tenant.subscription.view")
    show_days = owners and p.subscription is not None and p.subscription.reminders_enabled
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        tenant = (
            await db.execute(
                select(Tenant.currency, Tenant.language, overrides_subquery()).where(
                    Tenant.id == p.tenant_id
                )
            )
        ).one()
        flags = sorted(resolve(tenant[2] or {}))
    return Capabilities(
        currency=tenant.currency,
        language=tenant.language,
        tenant_id=p.tenant_id,
        permissions=sorted((p.permissions & registry.permissions) - switched_off),
        all_outlets=p.all_outlets,
        outlet_ids=sorted(p.outlet_ids),
        modules=sorted(p.enabled_modules),
        subscription=SubscriptionBanner(
            state=p.subscription_state,
            days_left=days_left(p.subscription, datetime.now(UTC))
            if show_days and p.subscription
            else None,
        ),
        nav=nav,
        flags=flags,
    )
