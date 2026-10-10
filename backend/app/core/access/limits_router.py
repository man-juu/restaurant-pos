"""Per-role limits (docs/03 rule 7): maximum discount and similar, set by the owner per role.
Only permissions a module declares as limited can carry one, and only on roles that hold
the permission. No limit (null) means unlimited, as owners have by default."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.permissions import Registry
from app.core.access.policy import Principal, require
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Role, RolePermission
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/role-limits", tags=["roles"])
View = Annotated[Principal, Depends(require("tenant.settings.view"))]
Configure = Annotated[Principal, Depends(require("tenant.settings.configure"))]


class LimitOut(BaseModel):
    permission: str
    unit: str  # "bp" (basis points of a percentage) or "amount" (minor units)
    value: int | None


class RoleLimitsOut(BaseModel):
    role_id: uuid.UUID
    name: str
    limits: list[LimitOut]


class LimitsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limits: dict[str, Annotated[int, Field(ge=0, le=10**12)] | None] = Field(max_length=20)


async def _role_limits(db: AsyncSession, units: dict[str, str]) -> list[RoleLimitsOut]:
    roles = list(
        await db.scalars(select(Role).where(Role.tenant_id.is_not(None)).order_by(Role.name))
    )
    rows = (
        await db.execute(
            select(
                RolePermission.role_id, RolePermission.permission_code, RolePermission.limit_value
            ).where(RolePermission.permission_code.in_(units))
        )
    ).all()
    held: dict[uuid.UUID, list[LimitOut]] = {}
    for role_id, code, value in rows:
        held.setdefault(role_id, []).append(
            LimitOut(permission=code, unit=units[code], value=value)
        )
    return [
        RoleLimitsOut(
            role_id=r.id, name=r.name, limits=sorted(held[r.id], key=lambda x: x.permission)
        )
        for r in roles
        if r.id in held
    ]


@router.get("", response_model=list[RoleLimitsOut])
async def list_limits(request: Request, p: View) -> list[RoleLimitsOut]:
    registry: Registry = request.app.state.permission_registry
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await _role_limits(db, registry.limit_units)


@router.put("/{role_id}", response_model=list[RoleLimitsOut])
async def set_limits(
    role_id: uuid.UUID, body: LimitsIn, request: Request, p: Configure
) -> list[RoleLimitsOut]:
    registry: Registry = request.app.state.permission_registry
    if unknown := body.limits.keys() - registry.limit_units.keys():
        raise ConflictError("not_a_limited_permission", details={"permissions": sorted(unknown)})
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        role = await db.get(Role, role_id)
        if role is None or role.tenant_id is None:  # platform templates are read-only
            raise NotFoundError("role_not_found")
        for code, value in body.limits.items():
            if registry.limit_units[code] == "bp" and value is not None and value > 10_000:
                raise ConflictError("limit_above_100_percent", details={"permission": code})
            done = await db.execute(
                update(RolePermission)
                .where(RolePermission.role_id == role_id, RolePermission.permission_code == code)
                .values(limit_value=value)
            )
            if done.rowcount == 0:  # type: ignore[attr-defined]
                raise ConflictError("role_lacks_permission", details={"permission": code})
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="tenant.role.limits",
            target_type="role",
            target_id=role_id,
            summary={"limits": body.limits},
        )
        return await _role_limits(db, registry.limit_units)
