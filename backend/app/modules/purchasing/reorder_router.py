"""Reorder suggestions per outlet (FR-INV-013) and vendor ranking per item (FR-PUR-007).
Whoever may create purchase orders may see them; a draft PO is then created through the
normal order endpoint."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import tenant_today
from app.modules.purchasing import permissions as perm
from app.modules.purchasing import reorder, vendor_rank
from app.modules.purchasing.models import Vendor
from app.modules.purchasing.schemas import SuggestionGroup, VendorScoreOut

router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

Create = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]


@router.get("/reorder-suggestions", response_model=list[SuggestionGroup])
async def reorder_suggestions(
    outlet_id: uuid.UUID, request: Request, p: Create, lang: Literal["en", "id"] = "en"
) -> list[SuggestionGroup]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await reorder.suggestions(db, p.tenant_id, outlet_id, lang)


def _pct(v: Decimal | None) -> Decimal | None:
    return None if v is None else (v * 100).quantize(Decimal("0.1"))


@router.get("/vendor-ranking", response_model=list[VendorScoreOut])
async def vendor_ranking(item_id: uuid.UUID, request: Request, p: Create) -> list[VendorScoreOut]:
    """FR-PUR-007: the vendors that sell an item, best first by price, lead time, reliability."""
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        today = await tenant_today(db, p.tenant_id)
        ranked = (await vendor_rank.scores(db, p.tenant_id, {item_id}, today)).get(item_id, [])
        ids = [s.vendor_id for s in ranked]
        rows = await db.execute(select(Vendor.id, Vendor.name).where(Vendor.id.in_(ids)))
        names = dict(rows.tuples().all())
    return [
        VendorScoreOut(
            vendor_id=s.vendor_id,
            vendor_name=names.get(s.vendor_id, ""),
            per_base=s.per_base.quantize(Decimal("0.0001")),
            lead_days=s.lead_days,
            on_time_pct=_pct(s.on_time),
            fill_pct=_pct(s.fill),
            effective=s.effective.quantize(Decimal("0.0001")),
            preferred=s.preferred,
        )
        for s in ranked
    ]
