"""What other modules may use from inventory (module boundaries, CLAUDE.md rule 4).

Documents in other modules (purchasing, production, transfers, sales) post stock only through
these functions, inside their own transaction, so the ledger keeps one writer."""

from app.modules.inventory.bridges import BatchInfo, batch_details, loss_adjustment
from app.modules.inventory.events import STOCK_POSTED
from app.modules.inventory.forecast import Forecast, forecasts, needs_with_eoq
from app.modules.inventory.levels import below_par, par_and_on_hand
from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.planning import Need, producible, reorder_needs
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
    "STOCK_POSTED",
    "BatchInfo",
    "Forecast",
    "InLine",
    "Need",
    "OutLine",
    "Posting",
    "StockError",
    "batch_details",
    "below_par",
    "consume",
    "forecasts",
    "loss_adjustment",
    "needs_with_eoq",
    "negative_allowed",
    "par_and_on_hand",
    "producible",
    "receive",
    "reorder_needs",
    "reverse",
    "visible_outlet",
]
