"""Modules per outlet, set by the owner (FR-TEN-003, owner 2026-10-10). The platform admin
decides which modules the business may use; the owner then switches each one on or off per
outlet (all outlets alike, or some with their own set). A module can only be on at an
outlet where the modules it needs are on too. Enforced on every request by the access
policy: an outlet whose module is off is invisible to that module's routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.models import Outlet, OutletModuleOff
from app.core.module_catalog import OPTIONAL_MODULES, ModuleDependencyError
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/outlet-modules", tags=["tenant"])

Configure = Annotated[Principal, Depends(require("tenant.module.configure"))]


class OutletModulesRow(BaseModel):
    outlet_id: uuid.UUID
    name: str
    off: list[str]


class OutletModulesOut(BaseModel):
    modules: list[str]  # the optional modules this business has, in dependency order
    depends_on: dict[str, list[str]]
    outlets: list[OutletModulesRow]


class OutletModulesIn(BaseModel):
    off: dict[uuid.UUID, list[str]] = Field(default_factory=dict, max_length=500)


def _tenant_modules(p: Principal) -> list[str]:
    return [m for m in OPTIONAL_MODULES if m in p.enabled_modules]


def check(modules: list[str], off: dict[uuid.UUID, list[str]]) -> None:
    """Every switched-off name is a module of this business, and nothing on lacks a module
    it needs at the same outlet."""
    if unknown := {m for names in off.values() for m in names} - set(modules):
        raise ModuleDependencyError("unknown_module", details={"modules": sorted(unknown)})
    missing = sorted(
        f"{outlet}:{m}->{dep}"
        for outlet, names in off.items()
        for m in set(modules) - set(names)
        for dep in OPTIONAL_MODULES[m]
        if dep in names
    )
    if missing:
        raise ModuleDependencyError(details={"missing": missing})


@router.get("", response_model=OutletModulesOut)
async def get_outlet_modules(request: Request, p: Configure) -> OutletModulesOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        outlets = (await db.execute(select(Outlet.id, Outlet.name).order_by(Outlet.name))).all()
    modules = _tenant_modules(p)
    off: dict[uuid.UUID, list[str]] = {}
    for outlet, module in sorted(p.modules_off, key=lambda x: x[1]):
        off.setdefault(outlet, []).append(module)
    return OutletModulesOut(
        modules=modules,
        depends_on={m: [d for d in OPTIONAL_MODULES[m] if d in modules] for m in modules},
        outlets=[OutletModulesRow(outlet_id=i, name=n, off=off.get(i, [])) for i, n in outlets],
    )


@router.put("", status_code=204)
async def put_outlet_modules(body: OutletModulesIn, request: Request, p: Configure) -> None:
    """Replaces the whole table: outlets left out get every module."""
    off = {o: sorted(set(names)) for o, names in body.off.items() if names}
    check(_tenant_modules(p), off)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        known = set(await db.scalars(select(Outlet.id)))
        off = {o: names for o, names in off.items() if o in known}
        await db.execute(delete(OutletModuleOff))
        rows = [
            {"tenant_id": p.tenant_id, "outlet_id": o, "module": m}
            for o, names in off.items()
            for m in names
        ]
        if rows:
            await db.execute(insert(OutletModuleOff), rows)
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="tenant.outlet_modules.set",
            summary={"off": {str(o): names for o, names in off.items()}},
        )
