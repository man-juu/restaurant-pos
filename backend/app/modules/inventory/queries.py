"""Read side of the ledger: stock on hand, batches, movement history, valuation at a date
(FR-INV-001, FR-INV-014) and the tenant-wide unit costs the catalog uses (FR-CAT-007)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, paginate
from app.modules.catalog.interface import item_names
from app.modules.inventory.models import ItemCost, StockBalance, StockBatch, StockMovement
from app.modules.inventory.schemas import BatchOut, MovementOut, StockRow, ValuationRow
from app.modules.inventory.service import money


def _col(column: Any) -> ColumnElement[Any]:
    return cast(ColumnElement[Any], column)


@dataclass(frozen=True)
class Viewer:
    """Who reads: names in their language; costs only with catalog.cost.view."""

    tenant_id: uuid.UUID
    language: str
    show_cost: bool


async def _labels(db: AsyncSession, v: Viewer, ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    names = await item_names(db, v.tenant_id, v.language, ids)
    return {i: {"sku": n.sku, "name": n.name, "unit_code": n.unit_code} for i, n in names.items()}


async def on_hand(
    db: AsyncSession, outlet_id: uuid.UUID, params: PageParams, v: Viewer
) -> tuple[list[StockRow], str | None]:
    """One row per item with stock (or a shortage) at the outlet."""
    totals = (
        select(StockBalance.item_id, func.sum(StockBalance.qty).label("qty"))
        .where(StockBalance.outlet_id == outlet_id)
        .group_by(StockBalance.item_id)
        .having(func.sum(StockBalance.qty) != 0)
        .subquery()
    )
    stmt = select(totals.c.item_id, totals.c.qty, ItemCost.avg_cost).outerjoin(
        ItemCost, (ItemCost.item_id == totals.c.item_id) & (ItemCost.outlet_id == outlet_id)
    )
    item_id = _col(totals.c.item_id)
    rows, cursor = await paginate(
        db,
        cast(Select[Any], stmt),
        params,
        id_column=item_id,
        sortable={"item_id": item_id},
        default_sort="item_id",
    )
    labels = await _labels(db, v, [r[0] for r in rows])
    out = []
    for i, qty, avg in rows:
        cost = avg if v.show_cost else None
        value = money(qty, avg) if v.show_cost and avg is not None else None
        out.append(StockRow(item_id=i, qty=qty, avg_cost=cost, value=value, **labels[i]))
    return out, cursor


async def batches(db: AsyncSession, outlet_id: uuid.UUID, item_id: uuid.UUID) -> list[BatchOut]:
    """Batches still holding stock, in the order FEFO will use them."""
    stmt = (
        select(StockBatch, StockBalance.qty)
        .join(StockBalance, StockBalance.batch_id == StockBatch.id)
        .where(
            StockBalance.outlet_id == outlet_id,
            StockBalance.item_id == item_id,
            StockBalance.qty != 0,
        )
        .order_by(StockBatch.expiry_date.asc().nulls_last(), StockBatch.received_at)
        .limit(500)
    )
    return [
        BatchOut(
            id=b.id,
            lot_code=b.lot_code,
            expiry_date=b.expiry_date,
            received_at=b.received_at,
            qty=qty,
        )
        for b, qty in (await db.execute(stmt)).all()
    ]


async def movements(
    db: AsyncSession,
    outlet_id: uuid.UUID,
    item_id: uuid.UUID | None,
    params: PageParams,
    *,
    show_cost: bool,
) -> tuple[list[MovementOut], str | None]:
    stmt = select(StockMovement).where(StockMovement.outlet_id == outlet_id)
    if item_id:
        stmt = stmt.where(StockMovement.item_id == item_id)
    # UUIDv7 ids grow with time, so newest-first by id is newest-first by posting.
    mid = _col(StockMovement.id)
    rows, cursor = await paginate(
        db, cast(Select[Any], stmt), params, id_column=mid, sortable={"id": mid}, default_sort="-id"
    )
    return [_movement_out(m, show_cost) for m in rows], cursor


def _movement_out(m: StockMovement, show_cost: bool) -> MovementOut:
    return MovementOut(
        id=m.id,
        item_id=m.item_id,
        batch_id=m.batch_id,
        movement_type=m.movement_type,
        qty=m.qty,
        unit_cost=m.unit_cost if show_cost else None,
        value=m.value if show_cost else None,
        doc_type=m.doc_type,
        doc_id=m.doc_id,
        business_date=m.business_date,
        posted_at=m.posted_at,
        reverses_id=m.reverses_id,
    )


async def valuation(
    db: AsyncSession, outlet_id: uuid.UUID, on: date, params: PageParams, v: Viewer
) -> tuple[list[ValuationRow], str | None]:
    """FR-INV-014 (docs/05 rule 9): quantity and value per item at the end of `on`, summed
    from the movements, so any past date can be reproduced exactly."""
    totals = (
        select(
            StockMovement.item_id,
            func.sum(StockMovement.qty).label("qty"),
            func.sum(StockMovement.value).label("value"),
        )
        .where(StockMovement.outlet_id == outlet_id, StockMovement.business_date <= on)
        .group_by(StockMovement.item_id)
        .having((func.sum(StockMovement.qty) != 0) | (func.sum(StockMovement.value) != 0))
        .subquery()
    )
    stmt = select(totals.c.item_id, totals.c.qty, totals.c.value)
    item_id = _col(totals.c.item_id)
    rows, cursor = await paginate(
        db,
        cast(Select[Any], stmt),
        params,
        id_column=item_id,
        sortable={"item_id": item_id},
        default_sort="item_id",
    )
    labels = await _labels(db, v, [r[0] for r in rows])
    return [
        ValuationRow(item_id=i, qty=q, value=int(val), **labels[i]) for i, q, val in rows
    ], cursor


async def tenant_unit_costs(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Cost source for recipe costing: the stock-weighted average over outlets that hold the
    item, else the highest known average. Items never received have no cost (unknown)."""
    held = ItemCost.qty_on_hand_for_avg > 0
    weighted = func.sum(ItemCost.avg_cost * ItemCost.qty_on_hand_for_avg).filter(
        held
    ) / func.nullif(func.sum(ItemCost.qty_on_hand_for_avg).filter(held), 0)
    stmt = (
        select(ItemCost.item_id, func.coalesce(weighted, func.max(ItemCost.avg_cost)))
        .where(ItemCost.item_id.in_(ids), ItemCost.avg_cost > 0)
        .group_by(ItemCost.item_id)
    )
    return {i: Decimal(c).quantize(Decimal("0.000001")) for i, c in (await db.execute(stmt)).all()}
