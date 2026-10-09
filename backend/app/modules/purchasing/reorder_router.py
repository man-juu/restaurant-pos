"""Reorder suggestions per outlet (FR-INV-013). Whoever may create purchase orders may see
what to reorder; the draft PO is then created through the normal order endpoint."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.purchasing import permissions as perm
from app.modules.purchasing import reorder
from app.modules.purchasing.schemas import SuggestionGroup

router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

Create = Annotated[Principal, Depends(require(perm.ORDER_CREATE))]


@router.get("/reorder-suggestions", response_model=list[SuggestionGroup])
async def reorder_suggestions(
    outlet_id: uuid.UUID, request: Request, p: Create, lang: Literal["en", "id"] = "en"
) -> list[SuggestionGroup]:
    p.require_outlet(outlet_id)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        return await reorder.suggestions(db, p.tenant_id, outlet_id, lang)
