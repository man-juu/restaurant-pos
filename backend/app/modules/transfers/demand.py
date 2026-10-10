"""Open branch requests as demand on the sending outlet (FR-PRD-008 with FR-TRF-001):
requested or approved, not yet shipped, needed by the day (or with no date)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transfers.models import Transfer, TransferLine

OPEN = ("requested", "approved")


async def open_requests(
    db: AsyncSession, outlet_id: uuid.UUID, until: date
) -> dict[uuid.UUID, Decimal]:
    qty = func.coalesce(TransferLine.approved_qty, TransferLine.requested_qty)
    stmt = (
        select(TransferLine.item_id, func.sum(qty))
        .join(Transfer, Transfer.id == TransferLine.transfer_id)
        .where(
            Transfer.from_outlet_id == outlet_id,
            Transfer.status.in_(OPEN),
            or_(Transfer.needed_by.is_(None), Transfer.needed_by <= until),
        )
        .group_by(TransferLine.item_id)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all() if row[1] > 0}
