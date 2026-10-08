"""One-tap correction for estimated items (rice, oil, gas): "this is what is on hand now".
Posts an adjustment for the difference at once, without the approval flow: estimated items are
corrected often and by design never block anything (owner decision, docs/09 0.27, 0.31)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.interface import stock_items
from app.modules.inventory import documents, flow
from app.modules.inventory.doc_models import Adjustment
from app.modules.inventory.doc_schemas import AdjustmentIn
from app.modules.inventory.models import StockBalance
from app.modules.inventory.schemas import Strict

OnHand = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]


class SetOnHandIn(Strict):
    outlet_id: uuid.UUID
    item_id: uuid.UUID
    qty: OnHand  # what is on hand now (may be 0), in `unit_id`
    unit_id: uuid.UUID
    business_date: date


async def set_on_hand(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: SetOnHandIn
) -> Adjustment | None:
    """Returns the posted adjustment, or None when stock already matches."""
    item = (await stock_items(db, {data.item_id})).get(data.item_id)
    if item is None:
        raise NotFoundError("item_not_found")
    if not item.estimated:
        raise ConflictError("not_estimated")  # exact items go through counts and approvals
    target = (await flow.to_base(db, [(data.item_id, data.unit_id, data.qty)]))[data.item_id]
    current = await db.scalar(
        select(func.coalesce(func.sum(StockBalance.qty), 0)).where(
            StockBalance.outlet_id == data.outlet_id, StockBalance.item_id == data.item_id
        )
    )
    diff = target - Decimal(current or 0)
    if diff == 0:
        return None
    adj = await documents.save_adjustment(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        data=AdjustmentIn.model_validate(
            {
                "outlet_id": data.outlet_id,
                "business_date": data.business_date,
                "reason_code": "correction",
                "note": "Set on hand (estimated item)",
                "lines": [{"item_id": data.item_id, "qty": diff, "unit_id": item.base_unit_id}],
            }
        ),
    )
    await documents.post_now(db, adj, user_id)
    return adj
