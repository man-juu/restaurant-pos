"""Reading stock documents with their lines and item names."""

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.catalog.interface import item_names
from app.modules.inventory.doc_models import (
    Adjustment,
    AdjustmentLine,
    StockCount,
    StockCountLine,
    WasteLine,
    WasteLog,
)
from app.modules.inventory.doc_schemas import DocLine, StockDocument

Kind = Literal["waste", "adjustment", "count"]
HEADERS: dict[Kind, Any] = {"waste": WasteLog, "adjustment": Adjustment, "count": StockCount}
LINES: dict[Kind, tuple[Any, Any]] = {
    "waste": (WasteLine, WasteLine.waste_id),
    "adjustment": (AdjustmentLine, AdjustmentLine.adjustment_id),
    "count": (StockCountLine, StockCountLine.count_id),
}
LIST_LIMIT = 100


def _header(kind: Kind, doc: Any) -> StockDocument:
    return StockDocument(
        id=doc.id,
        kind=kind,
        number=doc.number,
        outlet_id=doc.outlet_id,
        business_date=doc.business_date,
        status=doc.status,
        reason_code=getattr(doc, "reason_code", None),
        count_type=getattr(doc, "count_type", None),
        blind=getattr(doc, "blind", False),
        note=doc.note,
        created_by=doc.created_by,
    )


async def list_documents(db: AsyncSession, kind: Kind, outlet_id: uuid.UUID) -> list[StockDocument]:
    model = HEADERS[kind]
    stmt = (
        select(model)
        .where(model.outlet_id == outlet_id)
        .order_by(model.id.desc())  # UUIDv7: newest first
        .limit(LIST_LIMIT)
    )
    return [_header(kind, d) for d in (await db.execute(stmt)).scalars()]


async def get_document(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: Kind,
    doc_id: uuid.UUID,
    language: str,
    show_system: bool,
) -> StockDocument:
    """`show_system` False hides frozen quantities of a blind count that is still open."""
    doc = await db.get(HEADERS[kind], doc_id)
    if doc is None:
        raise NotFoundError("document_not_found")
    line_model, parent = LINES[kind]
    rows = list((await db.execute(select(line_model).where(parent == doc_id))).scalars())
    names = await item_names(db, tenant_id, language, (r.item_id for r in rows))
    hide = kind == "count" and doc.blind and doc.status == "draft" and not show_system
    out = _header(kind, doc)
    out.lines = [
        DocLine(
            item_id=r.item_id,
            sku=names[r.item_id].sku,
            name=names[r.item_id].name,
            unit_code=names[r.item_id].unit_code,
            qty=getattr(r, "qty", None),
            unit_id=getattr(r, "unit_id", None),
            system_qty=None if hide else getattr(r, "system_qty", None),
            counted_qty=getattr(r, "counted_qty", None),
        )
        for r in rows
    ]
    return out
