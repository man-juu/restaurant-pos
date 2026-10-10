"""Opening balances: the stock an outlet holds when it starts using the system (FR-INV-002
"opening balance"; bulk import arrives with slice 1d). It must come before any other
movement of the item at that outlet, and a mistake is undone by a reversal (FR-X-005)."""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.models import Outlet
from app.modules.catalog.interface import base_factors, tenant_today
from app.modules.inventory.models import StockMovement
from app.modules.inventory.schemas import OpeningIn, PostedDocument
from app.modules.inventory.service import COST, InLine, Posting, receive, reverse

DOC_TYPE = "opening_balance"
QTY = Decimal("0.0001")


async def visible_outlet(db: AsyncSession, outlet_id: uuid.UUID) -> Outlet:
    """Under RLS another tenant's outlet does not exist; inactive outlets take no stock."""
    outlet = await db.get(Outlet, outlet_id)
    if outlet is None or not outlet.is_active:
        raise NotFoundError("outlet_not_found")
    return outlet


async def post_opening(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: OpeningIn
) -> PostedDocument:
    await visible_outlet(db, data.outlet_id)
    ids = {ln.item_id for ln in data.lines}
    started = await db.scalar(
        select(StockMovement.item_id)
        .where(StockMovement.outlet_id == data.outlet_id, StockMovement.item_id.in_(ids))
        .limit(1)
    )
    if started is not None:
        raise ConflictError("opening_after_movements", details={"item_id": str(started)})
    factors = await base_factors(db, {(ln.item_id, ln.unit_id) for ln in data.lines})
    lines = []
    for ln in data.lines:
        f = factors[(ln.item_id, ln.unit_id)]
        lines.append(
            InLine(
                item_id=ln.item_id,
                qty=(ln.qty * f).quantize(QTY, rounding=ROUND_HALF_UP),
                unit_cost=(ln.unit_cost / f).quantize(COST, rounding=ROUND_HALF_UP),
                lot_code=ln.lot_code,
                expiry_date=ln.expiry_date,
            )
        )
    p = Posting(tenant_id, data.outlet_id, user_id, DOC_TYPE, uuid7(), data.business_date)
    moves = await receive(db, p, "opening_balance", lines)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=data.outlet_id,
        action="inventory.opening.post",
        target_type=DOC_TYPE,
        target_id=p.doc_id,
        summary={"lines": len(lines), "business_date": data.business_date.isoformat()},
    )
    return PostedDocument(doc_type=DOC_TYPE, doc_id=p.doc_id, movements=len(moves))


async def document_outlet(db: AsyncSession, doc_id: uuid.UUID) -> uuid.UUID:
    outlet = await db.scalar(
        select(StockMovement.outlet_id)
        .where(StockMovement.doc_type == DOC_TYPE, StockMovement.doc_id == doc_id)
        .limit(1)
    )
    if outlet is None:
        raise NotFoundError("document_not_found")
    return outlet


async def reverse_opening(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, doc_id: uuid.UUID
) -> PostedDocument:
    outlet_id = await document_outlet(db, doc_id)
    today = await tenant_today(db, tenant_id)
    p = Posting(tenant_id, outlet_id, user_id, DOC_TYPE, doc_id, today)
    moves = await reverse(db, p, DOC_TYPE, doc_id)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=outlet_id,
        action="inventory.opening.reverse",
        target_type=DOC_TYPE,
        target_id=doc_id,
        summary={"movements": len(moves)},
    )
    return PostedDocument(doc_type=DOC_TYPE, doc_id=doc_id, movements=len(moves))
