"""Lot traceability (FR-INV-016), read from the stock ledger alone.

A document that takes stock out of a batch and creates new batches links them: production
consumes ingredient batches and creates the output batch; a transfer takes a batch at the
source and creates the same lot at the destination. So:
- where a batch went: its outgoing movements, and the batches their documents created;
- where a batch came from: the document that created it, and the batches it took stock from.
Inventory never reads other modules' tables for this. The walk is bounded (depth, nodes) and
only shows outlets the caller may see (docs/03 outlet scope)."""

import uuid
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.catalog.interface import item_names
from app.modules.inventory.models import StockBatch, StockMovement

MAX_DEPTH = 6
MAX_BATCHES = 200
Doc = tuple[str, uuid.UUID]


class TraceBatch(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    sku: str
    name: str
    unit_code: str
    outlet_id: uuid.UUID
    lot_code: str | None
    expiry_date: date | None
    received_at: datetime
    source_doc_type: str
    depth: int  # steps from the batch traced


class TraceUse(BaseModel):
    """Stock taken out of a batch by one document (a sale, waste, production, transfer)."""

    batch_id: uuid.UUID
    doc_type: str
    doc_id: uuid.UUID
    outlet_id: uuid.UUID
    business_date: date
    qty: Decimal  # positive: how much left the batch
    made: list[uuid.UUID]  # batches this document created from it


class Trace(BaseModel):
    batch: TraceBatch
    sources: list[TraceBatch]  # what it was made from, nearest first
    descendants: list[TraceBatch]  # what was made from it or moved on, nearest first
    uses: list[TraceUse]  # every document that took stock out of it or its descendants
    hidden: int  # batches at outlets the caller may not see


async def _batches(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, StockBatch]:
    if not ids:
        return {}
    return {b.id: b for b in await db.scalars(select(StockBatch).where(StockBatch.id.in_(ids)))}


async def _made_by(db: AsyncSession, docs: set[Doc]) -> dict[Doc, list[StockBatch]]:
    if not docs:
        return {}
    key = tuple_(StockBatch.source_doc_type, StockBatch.source_doc_id)
    out: dict[Doc, list[StockBatch]] = {}
    for b in await db.scalars(select(StockBatch).where(key.in_(list(docs)))):
        out.setdefault((b.source_doc_type, b.source_doc_id), []).append(b)
    return out


def _children(parent: StockBatch, made: list[StockBatch]) -> list[StockBatch]:
    """A transfer moves the same item on; production turns it into another item. When the
    document created the same item again, only those batches came from this one."""
    same = [b for b in made if b.item_id == parent.item_id and b.id != parent.id]
    return same or [b for b in made if b.id != parent.id]


async def _outgoing(db: AsyncSession, ids: set[uuid.UUID]) -> list[tuple[Any, ...]]:
    stmt = (
        select(
            StockMovement.batch_id,
            StockMovement.doc_type,
            StockMovement.doc_id,
            StockMovement.outlet_id,
            func.min(StockMovement.business_date),
            -func.sum(StockMovement.qty),
        )
        .where(StockMovement.batch_id.in_(ids), StockMovement.qty < 0)
        .group_by(
            StockMovement.batch_id,
            StockMovement.doc_type,
            StockMovement.doc_id,
            StockMovement.outlet_id,
        )
    )
    return list((await db.execute(stmt)).all())


async def _step(
    db: AsyncSession, level: dict[uuid.UUID, StockBatch]
) -> tuple[list[TraceUse], dict[uuid.UUID, StockBatch]]:
    """One level down: the uses of these batches and the batches those documents made."""
    rows = await _outgoing(db, set(level))
    made = await _made_by(db, {(r[1], r[2]) for r in rows})
    uses, kids = [], {}
    for batch_id, doc_type, doc_id, outlet_id, day, qty in rows:
        children = _children(level[batch_id], made.get((doc_type, doc_id), []))
        kids.update({k.id: k for k in children})
        uses.append(
            TraceUse(
                batch_id=batch_id,
                doc_type=doc_type,
                doc_id=doc_id,
                outlet_id=outlet_id,
                business_date=day,
                qty=qty,
                made=[k.id for k in children],
            )
        )
    return uses, kids


async def _forward(
    db: AsyncSession, root: StockBatch
) -> tuple[dict[uuid.UUID, tuple[StockBatch, int]], list[TraceUse]]:
    seen: dict[uuid.UUID, tuple[StockBatch, int]] = {}
    uses: list[TraceUse] = []
    level = {root.id: root}
    for depth in range(1, MAX_DEPTH + 1):
        found, kids = await _step(db, level)
        uses += found
        level = {k: b for k, b in kids.items() if k not in seen and k != root.id}
        seen.update({k: (b, depth) for k, b in level.items()})
        if not level or len(seen) >= MAX_BATCHES:
            break
    return seen, uses


def _parents(child: StockBatch, taken: list[StockBatch]) -> list[StockBatch]:
    """Mirror of _children: a transfer's batch came only from batches of the same item."""
    same = [b for b in taken if b.item_id == child.item_id]
    return same or taken


async def _taken_by(db: AsyncSession, docs: set[Doc]) -> dict[Doc, list[StockBatch]]:
    key = tuple_(StockMovement.doc_type, StockMovement.doc_id)
    stmt = select(StockMovement.batch_id, StockMovement.doc_type, StockMovement.doc_id).where(
        key.in_(list(docs)), StockMovement.qty < 0, StockMovement.batch_id.is_not(None)
    )
    rows = [(r[0], r[1], r[2]) for r in (await db.execute(stmt)).all() if r[0] is not None]
    batches = await _batches(db, {r[0] for r in rows})
    out: dict[Doc, list[StockBatch]] = {}
    for batch_id, doc_type, doc_id in rows:
        found = out.setdefault((doc_type, doc_id), [])
        if batches[batch_id] not in found:
            found.append(batches[batch_id])
    return out


async def _backward(db: AsyncSession, root: StockBatch) -> dict[uuid.UUID, tuple[StockBatch, int]]:
    seen: dict[uuid.UUID, tuple[StockBatch, int]] = {}
    level = [root]
    for depth in range(1, MAX_DEPTH + 1):
        taken = await _taken_by(db, {(b.source_doc_type, b.source_doc_id) for b in level})
        nxt = []
        for child in level:
            for parent in _parents(
                child, taken.get((child.source_doc_type, child.source_doc_id), [])
            ):
                if parent.id not in seen and parent.id != root.id:
                    seen[parent.id] = (parent, depth)
                    nxt.append(parent)
        if not nxt or len(seen) >= MAX_BATCHES:
            break
        level = nxt
    return seen


def _node(b: StockBatch, names: dict[uuid.UUID, Any], depth: int) -> TraceBatch:
    n = names[b.item_id]
    return TraceBatch(
        id=b.id,
        item_id=b.item_id,
        sku=n.sku,
        name=n.name,
        unit_code=n.unit_code,
        outlet_id=b.outlet_id,
        lot_code=b.lot_code,
        expiry_date=b.expiry_date,
        received_at=b.received_at,
        source_doc_type=b.source_doc_type,
        depth=depth,
    )


async def trace(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    batch_id: uuid.UUID,
    language: str,
    visible: Callable[[uuid.UUID], bool],
) -> Trace:
    root = (await _batches(db, {batch_id})).get(batch_id)
    if root is None or not visible(root.outlet_id):
        raise NotFoundError("batch_not_found")
    up = await _backward(db, root)
    down, uses = await _forward(db, root)
    every = [(root, 0), *up.values(), *down.values()]
    names = await item_names(db, tenant_id, language, {b.item_id for b, _ in every})

    def node(b: StockBatch, depth: int) -> TraceBatch:
        return _node(b, names, depth)

    def shown(found: dict[uuid.UUID, tuple[StockBatch, int]]) -> list[TraceBatch]:
        rows = sorted(found.values(), key=lambda bd: (bd[1], bd[0].received_at))
        return [node(b, d) for b, d in rows if visible(b.outlet_id)]

    sources, descendants = shown(up), shown(down)
    return Trace(
        batch=node(root, 0),
        sources=sources,
        descendants=descendants,
        uses=[u for u in uses if visible(u.outlet_id)],
        hidden=len(up) + len(down) - len(sources) - len(descendants),
    )


async def find_lots(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    lot: str,
    language: str,
    visible: Callable[[uuid.UUID], bool],
) -> list[TraceBatch]:
    """Batches whose lot code starts with what was typed (case-insensitive), newest first."""
    pattern = lot.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    stmt = (
        select(StockBatch)
        .where(StockBatch.lot_code.ilike(pattern, escape="\\"))
        .order_by(StockBatch.received_at.desc())
        .limit(50)
    )
    rows = [b for b in await db.scalars(stmt) if visible(b.outlet_id)]
    names = await item_names(db, tenant_id, language, {b.item_id for b in rows})
    return [_node(b, names, 0) for b in rows]
