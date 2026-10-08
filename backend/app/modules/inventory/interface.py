"""What other modules may use from inventory (module boundaries, CLAUDE.md rule 4).

Documents in other modules (purchasing, production, transfers, sales) post stock only through
these functions, inside their own transaction, so the ledger keeps one writer."""

from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.policy import negative_allowed
from app.modules.inventory.service import (
    InLine,
    OutLine,
    Posting,
    StockError,
    consume,
    receive,
    reverse,
)

__all__ = [
    "InLine",
    "OutLine",
    "Posting",
    "StockError",
    "consume",
    "negative_allowed",
    "receive",
    "reverse",
    "visible_outlet",
]
