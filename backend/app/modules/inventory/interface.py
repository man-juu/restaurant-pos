"""What other modules may use from inventory (module boundaries, CLAUDE.md rule 4).

Documents in other modules (purchasing, production, transfers, sales) post stock only through
these functions, inside their own transaction, so the ledger keeps one writer."""

from app.modules.inventory.bridges import BatchInfo, batch_details, loss_adjustment
from app.modules.inventory.levels import below_par
from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.planning import Need, reorder_needs
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
    "BatchInfo",
    "InLine",
    "Need",
    "OutLine",
    "Posting",
    "StockError",
    "batch_details",
    "below_par",
    "consume",
    "loss_adjustment",
    "negative_allowed",
    "receive",
    "reorder_needs",
    "reverse",
    "visible_outlet",
]
