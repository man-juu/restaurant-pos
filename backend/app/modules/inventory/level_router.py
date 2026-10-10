"""Stock targets per outlet (docs/05 2.3, FR-PRD-008). Outlet scope on every call."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.inventory import levels
from app.modules.inventory import permissions as perm
from app.modules.inventory.schemas import LevelOut, LevelsIn

router = APIRouter(prefix="/api/v1/inventory/levels", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.LEVEL_MANAGE))]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


@router.get("", response_model=list[LevelOut])
async def list_levels(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[LevelOut]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await levels.list_levels(db, p.tenant_id, outlet_id, lang)


@router.put("", response_model=list[LevelOut])
async def save_levels(
    body: LevelsIn, request: Request, p: Manage, lang: Lang = "en"
) -> list[LevelOut]:
    p.require_outlet(body.outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await levels.save_levels(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        return await levels.list_levels(db, p.tenant_id, body.outlet_id, lang)
