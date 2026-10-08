"""Production orders (FR-PRD-001 to 004): plan -> complete (components out FEFO, output batch
in, in one transaction) -> reverse if needed; or cancel a plan. Stock is posted only through
the inventory interface (one ledger writer, CLAUDE.md rule 4)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.modules.catalog.interface import StockItem, item_names, recipe_needs, stock_items
from app.modules.inventory.interface import (
    InLine,
    OutLine,
    Posting,
    consume,
    negative_allowed,
    receive,
    reverse,
    visible_outlet,
)
from app.modules.production.models import ProductionLine, ProductionOrder
from app.modules.production.schemas import (
    ProductionCompleteIn,
    ProductionLineOut,
    ProductionOut,
    ProductionPlanIn,
)

DOC = "production"
OUTPUT_TYPES = frozenset({"semi_finished"})
QTY = Decimal("0.0001")
COST = Decimal("0.000001")


async def get_order(
    db: AsyncSession, order_id: uuid.UUID, *, lock: bool = False
) -> ProductionOrder:
    order = await db.get(ProductionOrder, order_id, with_for_update=lock)
    if order is None:
        raise NotFoundError("production_not_found")
    return order


async def order_lines(db: AsyncSession, order_id: uuid.UUID) -> list[ProductionLine]:
    stmt = select(ProductionLine).where(ProductionLine.order_id == order_id)
    return list(await db.scalars(stmt.order_by(ProductionLine.id)))


async def order_out(db: AsyncSession, order: ProductionOrder, lang: str = "en") -> ProductionOut:
    rows = await order_lines(db, order.id)
    names = await item_names(
        db, order.tenant_id, lang, {order.item_id, *(ln.item_id for ln in rows)}
    )
    lines = [
        ProductionLineOut.model_validate(ln, from_attributes=True).model_copy(
            update={"item_name": names[ln.item_id].name, "unit_code": names[ln.item_id].unit_code}
        )
        for ln in rows
    ]
    skip = ("lines", "yield_variance", "item_name", "unit_code")
    fields = {k: getattr(order, k) for k in ProductionOut.model_fields if k not in skip}
    variance = None if order.actual_qty is None else order.actual_qty - order.planned_qty
    label = names[order.item_id]
    return ProductionOut(
        **fields,
        item_name=label.name,
        unit_code=label.unit_code,
        yield_variance=variance,
        lines=lines,
    )


async def _audit(db: AsyncSession, order: ProductionOrder, user_id: uuid.UUID, action: str) -> None:
    await audit.record(
        db,
        tenant_id=order.tenant_id,
        user_id=user_id,
        outlet_id=order.outlet_id,
        action=f"production.order.{action}",
        target_type=DOC,
        target_id=order.id,
        summary={
            "number": order.number,
            "status": order.status,
            "actual_qty": str(order.actual_qty) if order.actual_qty is not None else None,
            "input_value": order.input_value,
        },
    )


def _ensure_status(order: ProductionOrder, *allowed: str) -> None:
    if order.status not in allowed:
        raise ConflictError("wrong_status", details={"status": order.status})


async def _output_item(db: AsyncSession, item_id: uuid.UUID) -> StockItem:
    item = (await stock_items(db, {item_id})).get(item_id)
    if item is None or not item.is_active:
        raise NotFoundError("item_not_found")
    if item.type not in OUTPUT_TYPES or not item.is_stocked:
        raise ConflictError("not_producible")
    return item


async def plan(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: ProductionPlanIn
) -> ProductionOrder:
    await visible_outlet(db, data.outlet_id)
    await _output_item(db, data.item_id)
    bom_id, needs = await recipe_needs(db, data.item_id, data.planned_qty, data.production_date)
    order = ProductionOrder(
        tenant_id=tenant_id,
        created_by=user_id,
        bom_id=bom_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC, on=data.production_date
        ),
        **data.model_dump(),
    )
    db.add(order)
    await db.flush()
    db.add_all(
        ProductionLine(
            tenant_id=tenant_id,
            order_id=order.id,
            item_id=item_id,
            planned_qty=qty.quantize(QTY, ROUND_HALF_UP),
            value=0,
        )
        for item_id, qty in needs.items()
    )
    await db.flush()
    await _audit(db, order, user_id, "plan")
    return order


async def _apply_used(
    db: AsyncSession, order: ProductionOrder, data: ProductionCompleteIn
) -> list[ProductionLine]:
    """Recipe quantities unless the cook says otherwise; extra components may be added."""
    lines = {ln.item_id: ln for ln in await order_lines(db, order.id)}
    extra = {u.item_id for u in data.used} - lines.keys()
    if order.item_id in extra:
        raise ConflictError("output_as_component")
    known = await stock_items(db, extra)
    if missing := extra - known.keys():
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, missing))})
    for item_id in extra:
        lines[item_id] = ProductionLine(
            tenant_id=order.tenant_id, order_id=order.id, item_id=item_id, planned_qty=0, value=0
        )
        db.add(lines[item_id])
    used = {u.item_id: u.qty for u in data.used}
    for ln in lines.values():
        ln.actual_qty = used.get(ln.item_id, ln.planned_qty)
    await db.flush()
    return list(lines.values())


def _posting(order: ProductionOrder, user_id: uuid.UUID) -> Posting:
    return Posting(order.tenant_id, order.outlet_id, user_id, DOC, order.id, order.production_date)


async def complete(
    db: AsyncSession, *, user_id: uuid.UUID, order_id: uuid.UUID, data: ProductionCompleteIn
) -> ProductionOrder:
    order = await get_order(db, order_id, lock=True)
    _ensure_status(order, "planned")
    output = await _output_item(db, order.item_id)
    lines = [ln for ln in await _apply_used(db, order, data) if ln.actual_qty]
    p = _posting(order, user_id)
    if lines:
        allowed = await negative_allowed(
            db, order.tenant_id, "production", confirmed=data.confirm_negative
        )
        outs = [OutLine(ln.item_id, ln.actual_qty, doc_line_id=ln.id) for ln in lines]  # type: ignore[arg-type]
        result = await consume(db, p, "production_consumption", outs, allow_negative=allowed)
        by_line: dict[uuid.UUID | None, int] = {}
        for m in result.movements:
            by_line[m.doc_line_id] = by_line.get(m.doc_line_id, 0) - m.value
        for ln in lines:
            ln.value = by_line.get(ln.id, 0)
    # FR-PRD-004: output cost = value of what was consumed / what really came out.
    order.input_value = sum(ln.value for ln in lines)
    order.actual_qty = data.actual_qty
    order.unit_cost = (Decimal(order.input_value) / data.actual_qty).quantize(COST, ROUND_HALF_UP)
    order.lot_code = data.lot_code or order.number
    order.expiry_date = data.expiry_date or (
        order.production_date + timedelta(days=output.shelf_life_days)
        if output.shelf_life_days is not None
        else None
    )
    await receive(
        db,
        p,
        "production_output",
        [
            InLine(
                order.item_id, data.actual_qty, order.unit_cost, order.lot_code, order.expiry_date
            )
        ],
    )
    order.status = "completed"
    order.completed_by = user_id
    order.completed_at = datetime.now(UTC)
    await _audit(db, order, user_id, "complete")
    return order


async def cancel(db: AsyncSession, *, user_id: uuid.UUID, order_id: uuid.UUID) -> ProductionOrder:
    order = await get_order(db, order_id, lock=True)
    _ensure_status(order, "planned")
    order.status = "cancelled"
    await _audit(db, order, user_id, "cancel")
    return order


async def reverse_order(
    db: AsyncSession, *, user_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrder:
    """FR-X-005: undo by reversal, only while the output batch still holds what was made."""
    order = await get_order(db, order_id, lock=True)
    _ensure_status(order, "completed")
    await reverse(db, _posting(order, user_id), DOC, order.id)
    order.status = "reversed"
    await _audit(db, order, user_id, "reverse")
    return order
