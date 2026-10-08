"""Purchasing service interface: vendors (vendors.py) and goods receipts (receipts.py)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.purchasing import receipts
from app.modules.purchasing.models import GoodsReceipt
from app.modules.purchasing.orders import (
    cancel,
    decide,
    get_order,
    order_out,
    receive,
    save_order,
    submit,
    undo_receipt_quantities,
)
from app.modules.purchasing.receipts import list_receipts, quick_purchase, receipt_out
from app.modules.purchasing.vendors import (
    add_vendor_item,
    get_vendor,
    list_vendor_items,
    list_vendors,
    reveal_bank_details,
    save_vendor,
)


async def reverse_receipt(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID
) -> GoodsReceipt:
    """Reverse the stock; a receipt against an order also gives the quantities back to it."""
    receipt = await receipts.reverse_receipt(db, user_id=user_id, receipt_id=receipt_id)
    await undo_receipt_quantities(db, receipt)
    return receipt


__all__ = [
    "add_vendor_item",
    "cancel",
    "decide",
    "get_order",
    "get_vendor",
    "list_receipts",
    "list_vendor_items",
    "list_vendors",
    "order_out",
    "quick_purchase",
    "receipt_out",
    "receive",
    "reveal_bank_details",
    "reverse_receipt",
    "save_order",
    "save_vendor",
    "submit",
]
