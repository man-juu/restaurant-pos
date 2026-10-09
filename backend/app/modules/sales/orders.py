"""POS orders (FR-SAL-004, 005): open an order, add lines with modifiers until it is paid,
send new lines to the kitchen, cancel an order nothing was made for. Every change locks the
order row and checks its status, so two tills cannot change one order at the same time.

Prices come from the channel's list price today plus the chosen options; the server works
out every total, the client only shows them."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.events import Event, publish
from app.core.settings import service as settings
from app.core.settings.pricing import Totals, calculate
from app.core.settings.schemas import ServiceChargeSettings, TaxSettings
from app.modules.catalog.interface import (
    SaleGroup,
    channel_code,
    item_names,
    prices_on,
    sale_groups,
    sold_out_at,
    stock_items,
    tenant_today,
)
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.discounts import discount_amount
from app.modules.sales.events import LINES_SENT, ORDER_CLOSED
from app.modules.sales.models import PosLineModifier, PosOrder, PosOrderLine
from app.modules.sales.pos_schemas import (
    PosLineIn,
    PosLineOut,
    PosLineUpdateIn,
    PosModifierOut,
    PosOrderCreateIn,
    PosOrderOut,
    PosTotalsOut,
)

DOC = "pos_order"


def line_total(qty: Decimal, unit_price: int) -> int:
    """docs/05 rule 2: round half up once per line, to whole minor units."""
    return int((qty * unit_price).quantize(Decimal(1), ROUND_HALF_UP))


async def get_order(db: AsyncSession, order_id: uuid.UUID, *, lock: bool = False) -> PosOrder:
    order = await db.get(PosOrder, order_id, with_for_update=lock)
    if order is None:
        raise NotFoundError("order_not_found")
    return order


def require_open(order: PosOrder) -> None:
    if order.status != "open":
        raise ConflictError("wrong_status", details={"status": order.status})


async def create_order(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: PosOrderCreateIn
) -> PosOrder:
    await visible_outlet(db, data.outlet_id)
    await channel_code(db, data.channel_id)  # an active channel of this tenant
    today = await tenant_today(db, tenant_id)
    number = await settings.allocate_number(db, tenant_id=tenant_id, doc_type=DOC, on=today)
    order = PosOrder(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        channel_id=data.channel_id,
        number=number,
        status="open",
        label=data.label,
        note=data.note,
        created_by=user_id,
    )
    db.add(order)
    await db.flush()
    await _audit(db, order, user_id, "create")
    return order


def _check_options(groups: list[SaleGroup], picked: list[uuid.UUID]) -> None:
    """Every option belongs to a group the item offers; each group's min and max hold."""
    if len(picked) != len(set(picked)):
        raise ConflictError("duplicate_option")
    offered = {o: g for g in groups for o in g.options}
    if unknown := set(picked) - offered.keys():
        raise NotFoundError("option_not_found", details={"ids": sorted(map(str, unknown))})
    for g in groups:
        count = sum(1 for o in picked if offered[o].id == g.id)
        if not g.min_select <= count <= g.max_select:
            raise ConflictError(
                "modifier_selection",
                details={"group": g.name, "min": g.min_select, "max": g.max_select},
            )


async def add_line(
    db: AsyncSession, order: PosOrder, *, user_id: uuid.UUID, data: PosLineIn
) -> PosOrderLine:
    require_open(order)
    item = (await stock_items(db, {data.item_id})).get(data.item_id)
    if item is None or not item.is_active or item.type != "menu":
        raise NotFoundError("item_not_found")
    if not item.is_available or await sold_out_at(db, order.outlet_id, {item.id}):
        raise ConflictError("item_sold_out")
    today = await tenant_today(db, order.tenant_id)
    price = (await prices_on(db, order.channel_id, {item.id}, today, order.outlet_id)).get(item.id)
    if price is None:
        raise ConflictError("price_missing", details={"item_ids": [str(item.id)]})
    groups = (await sale_groups(db, {item.id})).get(item.id, [])
    _check_options(groups, data.option_ids)
    options = {o.id: o for g in groups for o in g.options.values()}
    line = PosOrderLine(
        tenant_id=order.tenant_id,
        order_id=order.id,
        item_id=item.id,
        qty=data.qty,
        unit_price=price,
        note=data.note,
        status="new",
        created_by=user_id,
    )
    db.add(line)
    await db.flush()
    db.add_all(
        PosLineModifier(
            tenant_id=order.tenant_id,
            line_id=line.id,
            option_id=o,
            name=options[o].name,
            price_delta=options[o].price_delta,
        )
        for o in data.option_ids
    )
    await db.flush()
    return line


async def _line(db: AsyncSession, order: PosOrder, line_id: uuid.UUID) -> PosOrderLine:
    line = await db.get(PosOrderLine, line_id)
    if line is None or line.order_id != order.id:
        raise NotFoundError("line_not_found")
    if line.status != "new":
        # Sent lines were made in the kitchen: removing them is a void (FR-SAL-008).
        raise ConflictError("line_already_sent")
    return line


async def update_line(
    db: AsyncSession, order: PosOrder, line_id: uuid.UUID, data: PosLineUpdateIn
) -> None:
    require_open(order)
    line = await _line(db, order, line_id)
    line.qty, line.note = data.qty, data.note
    await db.flush()


async def remove_line(db: AsyncSession, order: PosOrder, line_id: uuid.UUID) -> None:
    require_open(order)
    line = await _line(db, order, line_id)
    await db.execute(delete(PosLineModifier).where(PosLineModifier.line_id == line.id))
    await db.delete(line)
    await db.flush()


async def send(db: AsyncSession, order: PosOrder, user_id: uuid.UUID) -> int:
    """FR-SAL-005 "sent to kitchen": new lines are now being made (the kitchen display and
    tickets read them, FR-KDS-001)."""
    require_open(order)
    lines = list(
        await db.scalars(
            select(PosOrderLine).where(
                PosOrderLine.order_id == order.id, PosOrderLine.status == "new"
            )
        )
    )
    await mark_sent(db, order, lines, user_id)
    if lines:
        await _audit(db, order, user_id, "send", {"lines": len(lines)})
    return len(lines)


async def mark_sent(
    db: AsyncSession, order: PosOrder, lines: list[PosOrderLine], user_id: uuid.UUID
) -> None:
    """New lines go to the kitchen: status "sent" and the kitchen hears of them."""
    fresh = [ln for ln in lines if ln.status == "new"]
    if not fresh:
        return
    now = datetime.now(UTC)
    for line in fresh:
        line.status, line.sent_at = "sent", now
    await db.flush()
    await announce(db, order, user_id, LINES_SENT, line_ids=[ln.id for ln in fresh])


async def cancel(db: AsyncSession, order: PosOrder, user_id: uuid.UUID) -> None:
    """Only while nothing was sent; after that it is a void with a reason (FR-SAL-008)."""
    require_open(order)
    sent = await db.scalar(
        select(func.count())
        .select_from(PosOrderLine)
        .where(PosOrderLine.order_id == order.id, PosOrderLine.status == "sent")
    )
    if sent:
        raise ConflictError("order_has_sent_lines")
    order.status = "cancelled"
    await db.flush()
    await _audit(db, order, user_id, "cancel")
    await announce(db, order, user_id, ORDER_CLOSED)


async def lines_of(db: AsyncSession, order: PosOrder, language: str) -> list[PosLineOut]:
    lines = list(
        await db.scalars(
            select(PosOrderLine)
            .where(PosOrderLine.order_id == order.id)
            .order_by(PosOrderLine.created_at, PosOrderLine.id)
        )
    )
    mods: dict[uuid.UUID, list[PosModifierOut]] = {}
    stmt = select(PosLineModifier).where(PosLineModifier.line_id.in_([ln.id for ln in lines]))
    for m in await db.scalars(stmt):
        mods.setdefault(m.line_id, []).append(
            PosModifierOut(option_id=m.option_id, name=m.name, price_delta=m.price_delta)
        )
    names = await item_names(db, order.tenant_id, language, {ln.item_id for ln in lines})
    out = []
    for ln in lines:
        unit = ln.unit_price + sum(m.price_delta for m in mods.get(ln.id, []))
        out.append(
            PosLineOut(
                id=ln.id,
                item_id=ln.item_id,
                name=names[ln.item_id].name if ln.item_id in names else "",
                qty=ln.qty,
                unit_price=unit,
                modifiers=mods.get(ln.id, []),
                line_total=line_total(ln.qty, unit),
                discount=0
                if ln.status == "void"
                else discount_amount(line_total(ln.qty, unit), ln.discount_kind, ln.discount_value),
                discount_reason=ln.discount_reason,
                note=ln.note,
                status=ln.status,  # type: ignore[arg-type]
                void_reason=ln.void_reason,
            )
        )
    return out


@dataclass(frozen=True)
class OrderTotals:
    gross: int  # live lines at their prices (with modifiers)
    discount: int  # line discounts plus the order discount (FR-SAL-007)
    taxed: Totals  # service charge and taxes on what is left (docs/05 section 6)


async def totals(db: AsyncSession, order: PosOrder, lines: list[PosLineOut]) -> OrderTotals:
    live = [ln for ln in lines if ln.status != "void"]
    gross = sum(ln.line_total for ln in live)
    net = gross - sum(ln.discount for ln in live)
    order_discount = discount_amount(net, order.discount_kind, order.discount_value)
    tax = cast(TaxSettings, await settings.get_setting(db, order.tenant_id, "tax"))
    sc = cast(
        ServiceChargeSettings, await settings.get_setting(db, order.tenant_id, "service_charge")
    )
    code = await channel_code(db, order.channel_id)
    taxed = calculate(
        [net - order_discount], tax=tax, service_charge=sc, channel=code, outlet_id=order.outlet_id
    )
    return OrderTotals(gross, gross - net + order_discount, taxed)


def totals_out(t: OrderTotals) -> PosTotalsOut:
    return PosTotalsOut(
        subtotal=t.gross,
        discount=t.discount,
        service_charge=t.taxed.service_charge,
        tax=t.taxed.tax_total,
        total=t.taxed.total,
    )


async def order_out(db: AsyncSession, order: PosOrder, language: str) -> PosOrderOut:
    lines = await lines_of(db, order, language)
    return PosOrderOut(
        id=order.id,
        number=order.number,
        status=order.status,  # type: ignore[arg-type]
        outlet_id=order.outlet_id,
        channel_id=order.channel_id,
        label=order.label,
        note=order.note,
        created_at=order.created_at,
        paid_at=order.paid_at,
        lines=lines,
        totals=totals_out(await totals(db, order, lines)),
        document_id=order.document_id,
        discount_kind=order.discount_kind,  # type: ignore[arg-type]
        discount_value=order.discount_value,
        discount_reason=order.discount_reason,
    )


async def _audit(
    db: AsyncSession,
    order: PosOrder,
    user_id: uuid.UUID,
    action: str,
    extra: dict[str, object] | None = None,
) -> None:
    await audit.record(
        db,
        tenant_id=order.tenant_id,
        user_id=user_id,
        outlet_id=order.outlet_id,
        action=f"sales.order.{action}",
        target_type="pos_order",
        target_id=order.id,
        summary={"number": order.number, **(extra or {})},
    )


async def announce(
    db: AsyncSession,
    order: PosOrder,
    user_id: uuid.UUID,
    name: str,
    line_ids: list[uuid.UUID] | None = None,
) -> None:
    """Tell other modules (tables, kitchen) in the same transaction (app/core/events.py)."""
    data: dict[str, object] = {
        "order_id": order.id,
        "outlet_id": order.outlet_id,
        "status": order.status,
    }
    if line_ids is not None:
        data["line_ids"] = line_ids
    await publish(db, Event(name, order.tenant_id, user_id, data))


async def move_lines(
    db: AsyncSession,
    src: PosOrder,
    dst: PosOrder,
    line_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> int:
    """FR-TBL-003 split bill by item: lines go to another open order of the same outlet and
    channel (the price stays as it was; nothing is posted until each order is paid)."""
    require_open(src)
    require_open(dst)
    if src.id == dst.id or (src.outlet_id, src.channel_id) != (dst.outlet_id, dst.channel_id):
        raise ConflictError("orders_not_compatible")
    rows = list(
        await db.scalars(
            select(PosOrderLine).where(
                PosOrderLine.id.in_(line_ids),
                PosOrderLine.order_id == src.id,
                PosOrderLine.status != "void",
            )
        )
    )
    if len(rows) != len(set(line_ids)):
        raise NotFoundError("line_not_found")
    for row in rows:
        row.order_id = dst.id
    await db.flush()
    await _audit(db, src, user_id, "move_lines", {"to": dst.number, "lines": len(rows)})
    return len(rows)
