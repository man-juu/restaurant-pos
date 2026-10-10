"""Finance listens to sales, inventory and purchasing (app/core/events.py) and journals what
they post (FR-FIN-003). Purchasing is named by its event strings only: finance does not
depend on that module, and the handlers simply never run where it is off."""

from app.core.events import subscribe
from app.modules.finance import auto
from app.modules.inventory.interface import STOCK_POSTED
from app.modules.sales.interface import DOCUMENT_POSTED, DOCUMENT_REVERSED

RECEIPT_POSTED = "purchasing.receipt.posted"
RECEIPT_REVERSED = "purchasing.receipt.reversed"
BILL_PAID = "purchasing.bill.paid"


def register() -> None:
    subscribe(STOCK_POSTED, "finance", auto.on_stock)
    subscribe(DOCUMENT_POSTED, "finance", auto.on_sale)
    subscribe(DOCUMENT_REVERSED, "finance", auto.on_sale_reversed)
    subscribe(RECEIPT_POSTED, "finance", auto.on_receipt)
    subscribe(RECEIPT_REVERSED, "finance", auto.on_receipt_reversed)
    subscribe(BILL_PAID, "finance", auto.on_bill_paid)
