"""Offline till endpoints (FR-SAL-013). The pack is fetched while online; each order taken
offline is uploaded once the connection is back. Outlet scope and permissions are the same
as for online orders: paying needs the pay permission."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError

from app.core.access.policy import PermissionDenied, Principal, require
from app.core.errors import ConflictError
from app.core.tenancy import tenant_session
from app.modules.sales import offline
from app.modules.sales import permissions as perm
from app.modules.sales.offline_schemas import OfflineOrderIn, OfflinePackOut, OfflineSyncOut

router = APIRouter(prefix="/api/v1/pos/offline", tags=["pos"])

Take = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]


@router.get("/pack", response_model=OfflinePackOut)
async def get_pack(channel_id: uuid.UUID, request: Request, p: Take) -> OfflinePackOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await offline.pack(db, p.tenant_id, channel_id)


@router.post("/orders", response_model=OfflineSyncOut)
async def sync_order(body: OfflineOrderIn, request: Request, p: Take) -> OfflineSyncOut:
    p.require_outlet(body.outlet_id)
    if body.payment is not None and not p.can(perm.ORDER_PAY):
        raise PermissionDenied(details={"permission": perm.ORDER_PAY})
    try:
        async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
            return await offline.sync(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
    except IntegrityError as e:  # two uploads of one order at the same moment: retry later
        raise ConflictError("offline_sync_busy") from e
