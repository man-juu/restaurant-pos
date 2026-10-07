"""Stock posting engine (FR-INV-001 to 006, FR-X-005, docs/05 section 3).

Every stock change in the system goes through `receive`, `consume` or `reverse`, inside the
caller's transaction, so a business document and its movements commit or fail together
(ledger rule 3). Purchasing (1f), production (1g), transfers (1h), counts (1i) and sales
(1k) call these functions; nothing else writes the ledger.

Concurrency: the item's cost row is locked first, then its batch balances, always in item-id
order, so two documents touching the same items queue instead of deadlocking.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError, ConflictError
from app.modules.catalog.interface import StockItem, stock_items
from app.modules.inventory.models import (
    INBOUND,
    OUTBOUND,
    ItemCost,
    StockBalance,
    StockBatch,
    StockMovement,
)

COST = Decimal("0.000001")
# FR-INV-003: goods arriving need an expiry date if they spoil. Stock found in a count or an
# adjustment has no delivery to read it from, so those may leave it empty.
EXPIRY_REQUIRED = frozenset({"purchase_receipt", "production_output", "opening_balance"})


class StockError(AppError):
    status_code, code = 422, "stock_error"


class InsufficientStock(AppError):
    status_code, code = 409, "insufficient_stock"


@dataclass(frozen=True)
class Posting:
    """Who posts what, where and for which business day."""

    tenant_id: uuid.UUID
    outlet_id: uuid.UUID
    user_id: uuid.UUID | None
    doc_type: str
    doc_id: uuid.UUID
    business_date: date


@dataclass(frozen=True)
class InLine:
    item_id: uuid.UUID
    qty: Decimal  # base unit, > 0
    unit_cost: Decimal  # per base unit
    lot_code: str | None = None
    expiry_date: date | None = None
    doc_line_id: uuid.UUID | None = None


@dataclass(frozen=True)
class OutLine:
    item_id: uuid.UUID
    qty: Decimal  # base unit, > 0
    batch_id: uuid.UUID | None = None  # FR-INV-004 override; the caller checks permission
    doc_line_id: uuid.UUID | None = None


@dataclass
class ConsumeResult:
    movements: list[StockMovement]
    short: dict[uuid.UUID, Decimal] = field(default_factory=dict)  # taken beyond on hand


def money(qty: Decimal, unit_cost: Decimal) -> int:
    """Line value in whole minor units, rounded half up (docs/05 section 6)."""
    return int((qty * unit_cost).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ─── Building blocks ──────────────────────────────────────────────────────


async def _stock_items(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, StockItem]:
    found = await stock_items(db, ids)
    if missing := ids - found.keys():
        raise StockError("invalid_reference", details={"item_ids": sorted(map(str, missing))})
    if not_stocked := [str(i) for i, item in found.items() if not item.is_stocked]:
        raise StockError("item_not_stocked", details={"item_ids": sorted(not_stocked)})
    return found


async def _cost_row(db: AsyncSession, p: Posting, item_id: uuid.UUID) -> ItemCost:
    """The item's moving-average row at the outlet, created on first use, locked."""
    await db.execute(
        pg_insert(ItemCost)
        .values(
            tenant_id=p.tenant_id,
            outlet_id=p.outlet_id,
            item_id=item_id,
            avg_cost=0,
            qty_on_hand_for_avg=0,
        )
        .on_conflict_do_nothing()
    )
    row = await db.scalar(
        select(ItemCost)
        .where(ItemCost.outlet_id == p.outlet_id, ItemCost.item_id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:  # cannot happen: inserted above under the same tenant
        raise StockError("cost_row_missing")
    return row


def average_in(row: ItemCost, qty: Decimal, unit_cost: Decimal) -> None:
    """Ledger rule 5: weighted average on stock coming in; reset when nothing is on hand."""
    old_qty = row.qty_on_hand_for_avg
    if old_qty <= 0:
        row.avg_cost = unit_cost
    else:
        row.avg_cost = ((old_qty * row.avg_cost + qty * unit_cost) / (old_qty + qty)).quantize(COST)
    row.qty_on_hand_for_avg = old_qty + qty


def average_out_at_cost(row: ItemCost, qty: Decimal, unit_cost: Decimal) -> None:
    """Undo a receipt: take `qty` out at the cost it came in at (invariant I-2: never < 0)."""
    remaining = row.qty_on_hand_for_avg - qty
    if remaining > 0:
        value = row.qty_on_hand_for_avg * row.avg_cost - qty * unit_cost
        row.avg_cost = max(Decimal(0), (value / remaining).quantize(COST))
    row.qty_on_hand_for_avg = remaining


async def _add_balance(
    db: AsyncSession, p: Posting, item_id: uuid.UUID, batch_id: uuid.UUID | None, qty: Decimal
) -> None:
    stmt = pg_insert(StockBalance).values(
        tenant_id=p.tenant_id, outlet_id=p.outlet_id, item_id=item_id, batch_id=batch_id, qty=qty
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_stock_balances_tenant_id_outlet_id_item_id_batch_id",
            set_={"qty": StockBalance.qty + stmt.excluded.qty},
        )
    )


async def _record(  # noqa: PLR0913 - one ledger row has this many facts
    db: AsyncSession,
    p: Posting,
    *,
    item_id: uuid.UUID,
    batch_id: uuid.UUID | None,
    movement_type: str,
    qty: Decimal,
    unit_cost: Decimal,
    doc_line_id: uuid.UUID | None,
    value: int | None = None,
    reverses_id: uuid.UUID | None = None,
) -> StockMovement:
    movement = StockMovement(
        tenant_id=p.tenant_id,
        outlet_id=p.outlet_id,
        item_id=item_id,
        batch_id=batch_id,
        movement_type=movement_type,
        qty=qty,
        unit_cost=unit_cost,
        value=money(qty, unit_cost) if value is None else value,
        doc_type=p.doc_type,
        doc_id=p.doc_id,
        doc_line_id=doc_line_id,
        business_date=p.business_date,
        posted_by=p.user_id,
        reverses_id=reverses_id,
    )
    db.add(movement)
    await _add_balance(db, p, item_id, batch_id, qty)
    return movement


# ─── Stock in ─────────────────────────────────────────────────────────────


async def receive(
    db: AsyncSession, p: Posting, movement_type: str, lines: list[InLine]
) -> list[StockMovement]:
    """Receipts, production output, transfers in, opening balances and positive corrections.
    Each line becomes a batch (FR-INV-003) and moves the average cost (FR-INV-005)."""
    if movement_type not in (*INBOUND, "adjustment", "count_correction"):
        raise StockError("wrong_movement_type")
    items = await _stock_items(db, {ln.item_id for ln in lines})
    movements = []
    for ln in sorted(lines, key=lambda x: x.item_id):
        needs_expiry = movement_type in EXPIRY_REQUIRED and items[ln.item_id].perishable
        if needs_expiry and ln.expiry_date is None:
            raise StockError("expiry_required", details={"item_id": str(ln.item_id)})
        cost = await _cost_row(db, p, ln.item_id)
        batch = StockBatch(
            tenant_id=p.tenant_id,
            outlet_id=p.outlet_id,
            item_id=ln.item_id,
            lot_code=ln.lot_code,
            expiry_date=ln.expiry_date,
            unit_cost=ln.unit_cost,
            source_doc_type=p.doc_type,
            source_doc_id=p.doc_id,
        )
        db.add(batch)
        await db.flush()
        average_in(cost, ln.qty, ln.unit_cost)
        movements.append(
            await _record(
                db,
                p,
                item_id=ln.item_id,
                batch_id=batch.id,
                movement_type=movement_type,
                qty=ln.qty,
                unit_cost=ln.unit_cost,
                doc_line_id=ln.doc_line_id,
            )
        )
    await db.flush()
    return movements


# ─── Stock out ────────────────────────────────────────────────────────────


async def _locked_batches(db: AsyncSession, p: Posting, item_id: uuid.UUID) -> list[StockBalance]:
    """Batches with stock, earliest expiry first, then oldest (ledger rule 4, FEFO)."""
    batch = aliased(StockBatch)
    stmt = (
        select(StockBalance)
        .join(batch, batch.id == StockBalance.batch_id)
        .where(
            StockBalance.outlet_id == p.outlet_id,
            StockBalance.item_id == item_id,
            StockBalance.qty > 0,
        )
        .order_by(batch.expiry_date.asc().nulls_last(), batch.received_at, batch.id)
        .with_for_update(of=StockBalance)
        .execution_options(populate_existing=True)
    )
    return list((await db.execute(stmt)).scalars())


async def _picks(
    db: AsyncSession, p: Posting, ln: OutLine
) -> tuple[list[tuple[uuid.UUID | None, Decimal]], Decimal]:
    """Which batches the quantity comes from, and how much is beyond what is on hand."""
    batches = await _locked_batches(db, p, ln.item_id)
    if ln.batch_id is not None:
        chosen = next((b for b in batches if b.batch_id == ln.batch_id), None)
        if chosen is None or chosen.qty < ln.qty:
            raise InsufficientStock("batch_insufficient", details={"batch_id": str(ln.batch_id)})
        return [(ln.batch_id, ln.qty)], Decimal(0)
    picks: list[tuple[uuid.UUID | None, Decimal]] = []
    remaining = ln.qty
    for bal in batches:
        if remaining <= 0:
            break
        take = min(bal.qty, remaining)
        picks.append((bal.batch_id, take))
        remaining -= take
    if remaining > 0:
        picks.append((None, remaining))  # negative stock, kept apart from real batches
    return picks, max(remaining, Decimal(0))


async def consume(
    db: AsyncSession,
    p: Posting,
    movement_type: str,
    lines: list[OutLine],
    *,
    allow_negative: bool,
) -> ConsumeResult:
    """Sales, production, transfers out, waste, returns and negative corrections, valued at
    the current average (FR-INV-005). Beyond on-hand stock only if `allow_negative`
    (FR-INV-006: the caller applies the tenant policy); the shortage is reported."""
    if movement_type not in (*OUTBOUND, "adjustment", "count_correction"):
        raise StockError("wrong_movement_type")
    await _stock_items(db, {ln.item_id for ln in lines})
    result = ConsumeResult(movements=[])
    for ln in sorted(lines, key=lambda x: x.item_id):
        cost = await _cost_row(db, p, ln.item_id)
        picks, short = await _picks(db, p, ln)
        if short and not allow_negative:
            raise InsufficientStock(details={"item_id": str(ln.item_id), "short": str(short)})
        if short:
            result.short[ln.item_id] = short
        for batch_id, qty in picks:
            result.movements.append(
                await _record(
                    db,
                    p,
                    item_id=ln.item_id,
                    batch_id=batch_id,
                    movement_type=movement_type,
                    qty=-qty,
                    unit_cost=cost.avg_cost,
                    doc_line_id=ln.doc_line_id,
                )
            )
        cost.qty_on_hand_for_avg -= ln.qty  # consumption never changes the average
    await db.flush()
    return result


# ─── Reversal (FR-X-005) ──────────────────────────────────────────────────


async def _open_movements(
    db: AsyncSession, doc_type: str, doc_id: uuid.UUID
) -> list[StockMovement]:
    reversal = aliased(StockMovement)
    stmt = (
        select(StockMovement)
        .outerjoin(reversal, reversal.reverses_id == StockMovement.id)
        .where(
            StockMovement.doc_type == doc_type,
            StockMovement.doc_id == doc_id,
            StockMovement.reverses_id.is_(None),
            reversal.id.is_(None),
        )
        .order_by(StockMovement.item_id, StockMovement.id)
    )
    return list((await db.execute(stmt)).scalars())


async def _batch_qty(db: AsyncSession, outlet_id: uuid.UUID, batch_id: uuid.UUID | None) -> Decimal:
    qty = await db.scalar(
        select(StockBalance.qty)
        .where(StockBalance.outlet_id == outlet_id, StockBalance.batch_id == batch_id)
        .with_for_update()
    )
    return qty or Decimal(0)


async def reverse(
    db: AsyncSession, p: Posting, doc_type: str, doc_id: uuid.UUID
) -> list[StockMovement]:
    """Post the exact opposite of every movement of a document that is not reversed yet.
    `p` carries who reverses it and on which business day; values mirror the originals,
    so valuation returns exactly to where it was."""
    originals = await _open_movements(db, doc_type, doc_id)
    if not originals:
        raise ConflictError("nothing_to_reverse")
    out = []
    for m in originals:
        where = Posting(p.tenant_id, m.outlet_id, p.user_id, doc_type, doc_id, p.business_date)
        cost = await _cost_row(db, where, m.item_id)
        if m.qty > 0:
            # Taking a receipt back is only possible while its batch still holds it.
            if await _batch_qty(db, m.outlet_id, m.batch_id) < m.qty:
                raise ConflictError("batch_already_used", details={"item_id": str(m.item_id)})
            average_out_at_cost(cost, m.qty, m.unit_cost)
        else:
            average_in(cost, -m.qty, m.unit_cost)
        out.append(
            await _record(
                db,
                where,
                item_id=m.item_id,
                batch_id=m.batch_id,
                movement_type=m.movement_type,
                qty=-m.qty,
                unit_cost=m.unit_cost,
                doc_line_id=m.doc_line_id,
                value=-m.value,
                reverses_id=m.id,
            )
        )
    await db.flush()
    return out
