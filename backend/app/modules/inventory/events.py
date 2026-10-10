"""Inventory events for other modules (app/core/events.py).

STOCK_POSTED: stock moved for a document (one engine call). Data: doc_type, doc_id,
outlet_id, business_date (ISO), values: {movement_type: signed value in minor units}. The
finance module turns it into a journal in the same transaction (FR-FIN-003)."""

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, publish
from app.modules.inventory.models import StockMovement

STOCK_POSTED = "inventory.stock.posted"


async def announce(db: AsyncSession, movements: list[StockMovement]) -> None:
    """One event per document and outlet with the value moved per movement type."""
    groups: dict[tuple[object, ...], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for m in movements:
        groups[(m.tenant_id, m.doc_type, m.doc_id, m.outlet_id, m.business_date)][
            m.movement_type
        ] += m.value
    for (tenant_id, doc_type, doc_id, outlet_id, day), values in groups.items():
        data = {
            "doc_type": doc_type,
            "doc_id": doc_id,
            "outlet_id": outlet_id,
            "business_date": day.isoformat(),  # type: ignore[attr-defined]
            "values": dict(values),
        }
        await publish(db, Event(STOCK_POSTED, tenant_id, None, data))  # type: ignore[arg-type]
