"""Purchasing events for other modules (app/core/events.py). Finance journals them
(FR-FIN-003); the stock side of a receipt is not journaled from the stock event, because only
purchasing knows whether a vendor will bill it (payable) or it was paid on the spot (cash).

RECEIPT_POSTED / RECEIPT_REVERSED: data receipt_id, outlet_id, business_date (ISO),
total, on_account (a vendor will bill it).
BILL_PAID: data bill_id, outlet_id, paid_on (ISO), amount (negative when a payment is
reversed), method_kind."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, publish
from app.modules.purchasing.models import GoodsReceipt

RECEIPT_POSTED = "purchasing.receipt.posted"
RECEIPT_REVERSED = "purchasing.receipt.reversed"
BILL_PAID = "purchasing.bill.paid"


async def receipt(
    db: AsyncSession, name: str, receipt: GoodsReceipt, user_id: uuid.UUID | None
) -> None:
    data = {
        "receipt_id": receipt.id,
        "outlet_id": receipt.outlet_id,
        "business_date": receipt.business_date.isoformat(),
        "total": receipt.total,
        "on_account": receipt.vendor_id is not None,  # a vendor will bill it
    }
    await publish(db, Event(name, receipt.tenant_id, user_id, data))


async def bill_paid(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    outlet_id: uuid.UUID,
    day: date,
    amount: int,
    method_kind: str,
) -> None:
    data = {
        "bill_id": bill_id,
        "outlet_id": outlet_id,
        "paid_on": day.isoformat(),
        "amount": amount,
        "method_kind": method_kind,
    }
    await publish(db, Event(BILL_PAID, tenant_id, user_id, data))
