"""Producible quantity per outlet (FR-INV-020). Outlet scope on every call."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import item_names, tenant_today
from app.modules.inventory import permissions as perm
from app.modules.inventory import planning
from app.modules.inventory.schemas import ProducibleRow

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


@router.get("/producible", response_model=list[ProducibleRow])
async def producible(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[ProducibleRow]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rows = await planning.producible(db, outlet_id, await tenant_today(db, p.tenant_id))
        ids = {r.item_id for r in rows} | {r.limiting_item_id for r in rows if r.limiting_item_id}
        names = await item_names(db, p.tenant_id, lang, ids)
    out = [
        ProducibleRow(
            item_id=r.item_id,
            name=names[r.item_id].name,
            unit_code=names[r.item_id].unit_code,
            can_make=r.can_make,
            limiting_item_id=r.limiting_item_id,
            limiting_name=names[r.limiting_item_id].name if r.limiting_item_id else None,
        )
        for r in rows
    ]
    return sorted(out, key=lambda r: (r.can_make, r.name.lower()))
