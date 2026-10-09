"""Tables listens to sales (app/core/events.py): paying or closing the last open bill of a
session frees its tables to "needs cleaning" (FR-TBL-002)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, subscribe
from app.modules.sales.interface import ORDER_CLOSED, ORDER_PAID
from app.modules.tables import service


async def _order_done(db: AsyncSession, event: Event) -> None:
    await service.close_if_done(db, uuid.UUID(str(event.data["order_id"])))


def register() -> None:
    for name in (ORDER_PAID, ORDER_CLOSED):
        subscribe(name, "tables", _order_done)
