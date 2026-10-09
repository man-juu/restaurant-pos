"""Three-way match (FR-PUR-009): what was ordered (PO), what arrived (goods receipts) and
what the vendor bills. Findings are stored on the bill for the accountant to review; whether
a flagged bill may still be paid is a tenant setting (purchasing.block_mismatched_payment)."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import base_factors
from app.modules.purchasing.ap_schemas import BillLineIn, MatchNote
from app.modules.purchasing.models import GoodsReceiptLine, PurchaseOrderLine

BP = Decimal(10_000)


async def ordered(db: AsyncSession, po_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """PO unit price per base unit, per item."""
    rows = list(await db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po_id)))
    factors = await base_factors(db, {(r.item_id, r.unit_id) for r in rows})
    return {r.item_id: Decimal(r.unit_price) / factors[(r.item_id, r.unit_id)] for r in rows}


async def received(db: AsyncSession, receipt_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Quantity received per item (base unit) on the given receipts."""
    if not receipt_ids:
        return {}
    stmt = select(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id.in_(receipt_ids))
    rows = list(await db.scalars(stmt))
    factors = await base_factors(db, {(r.item_id, r.unit_id) for r in rows})
    out: dict[uuid.UUID, Decimal] = {}
    for r in rows:
        out[r.item_id] = out.get(r.item_id, Decimal(0)) + r.qty * factors[(r.item_id, r.unit_id)]
    return out


def _issue(
    line: BillLineIn, got: Decimal, po_price: Decimal | None, has_po: bool, tolerance_bp: int
) -> str | None:
    price = Decimal(line.amount) / line.qty
    if has_po and po_price is None:
        return "not_on_po"
    if got <= 0:
        return "not_received"
    if line.qty > got:
        return "qty_over_received"
    if po_price is not None and price > po_price * (1 + Decimal(tolerance_bp) / BP):
        return "price_over_po"
    return None


def match(
    lines: list[BillLineIn],
    po_prices: dict[uuid.UUID, Decimal] | None,
    got: dict[uuid.UUID, Decimal],
    tolerance_bp: int,
) -> tuple[str, list[MatchNote]]:
    notes = []
    for ln in lines:
        po_price = (po_prices or {}).get(ln.item_id)
        qty = got.get(ln.item_id, Decimal(0))
        issue = _issue(ln, qty, po_price, po_prices is not None, tolerance_bp)
        if issue:
            notes.append(
                MatchNote(
                    item_id=ln.item_id,
                    issue=issue,  # type: ignore[arg-type]
                    billed_qty=ln.qty,
                    received_qty=qty,
                    billed_unit_price=(Decimal(ln.amount) / ln.qty).quantize(Decimal("0.000001")),
                    po_unit_price=po_price.quantize(Decimal("0.000001")) if po_price else None,
                )
            )
    if notes:
        return "mismatch", notes
    return ("matched" if po_prices is not None else "no_po"), notes
