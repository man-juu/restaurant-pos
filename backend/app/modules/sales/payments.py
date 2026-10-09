"""Paying a POS order (FR-SAL-006): one or more tenders, change from cash only, optional tip
and cash rounding by tenant setting. Payment posts the sales document, its lines, the
payments and the stock consumption in one transaction (CLAUDE.md rule 3), so a sale can
never exist without its stock movement or the other way round."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.pricing import round_half_up_div
from app.core.settings.schemas import PaymentMethod, PaymentMethodSettings, PosSettings
from app.modules.catalog.interface import option_ingredients, tenant_today
from app.modules.sales import discounts
from app.modules.sales.events import ORDER_PAID
from app.modules.sales.models import (
    Payment,
    PosLineModifier,
    PosOrder,
    PosOrderLine,
    SalesDocument,
    SalesLine,
    SalesModifierLine,
)
from app.modules.sales.orders import (
    OrderTotals,
    _audit,
    announce,
    lines_of,
    mark_sent,
    require_open,
    totals,
)
from app.modules.sales.pos_schemas import PosLineOut, PosPayIn, PosPaymentIn
from app.modules.sales.service import consume_for_sale, get_day
from app.modules.sales.shifts import current_shift

DOC = "pos_sale"


def cash_rounding(total: int, step: int) -> int:
    """docs/05 rule 6.5: round a cash bill half up to the step; returns the difference."""
    if step <= 1:
        return 0
    return round_half_up_div(total, step) * step - total


async def _methods(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, PaymentMethod]:
    found = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    return {m.code: m for m in found.methods if m.active}


def _tenders(
    payments: list[PosPaymentIn], methods: dict[str, PaymentMethod], due: int
) -> list[tuple[PosPaymentIn, PaymentMethod, int]]:
    """Check the tenders against the amount due; returns (tender, method, change)."""
    out = []
    for pay in payments:
        method = methods.get(pay.method)
        if method is None:
            raise NotFoundError("payment_method_not_found", details={"method": pay.method})
        tendered = pay.tendered if pay.tendered is not None else pay.amount
        if tendered < pay.amount or (method.kind != "cash" and tendered != pay.amount):
            # Only cash gives change; a card or QRIS charge is exactly what it pays.
            raise ConflictError("tendered_mismatch", details={"method": pay.method})
        out.append((pay, method, tendered - pay.amount))
    paid = sum(p.amount for p in payments)
    if paid != due:
        raise ConflictError("payment_total_mismatch", details={"due": due, "paid": paid})
    return out


def stock_quantities(
    lines: list[PosOrderLine], mods: list[tuple[uuid.UUID, Decimal, Decimal]]
) -> dict[uuid.UUID, Decimal]:
    """Menu items to expand by recipe, plus each option's ingredient change times the line
    quantity (negative for "without"; consumption adds it to the expanded recipe)."""
    qty: dict[uuid.UUID, Decimal] = {}
    for ln in lines:
        qty[ln.item_id] = qty.get(ln.item_id, Decimal(0)) + ln.qty
    for item_id, delta, line_qty in mods:
        qty[item_id] = qty.get(item_id, Decimal(0)) + delta * line_qty
    return qty


async def option_changes(
    db: AsyncSession, lines: list[PosOrderLine]
) -> list[tuple[uuid.UUID, Decimal, Decimal]]:
    by_line = {ln.id: ln for ln in lines}
    stmt = select(PosLineModifier.line_id, PosLineModifier.option_id).where(
        PosLineModifier.line_id.in_(by_line)
    )
    picked = (await db.execute(stmt)).all()
    changes = await option_ingredients(db, {o for _, o in picked})
    return [(*changes[o], by_line[line_id].qty) for line_id, o in picked if o in changes]


async def _post_document(
    db: AsyncSession,
    order: PosOrder,
    user_id: uuid.UUID,
    t: OrderTotals,
    tip: int,
    rounding: int,
) -> SalesDocument:
    today = await tenant_today(db, order.tenant_id)
    day = await get_day(db, order.tenant_id, order.outlet_id, today, lock=True)
    if day.status == "locked":
        raise ConflictError("day_locked")
    doc = SalesDocument(
        tenant_id=order.tenant_id,
        number=order.number,
        outlet_id=order.outlet_id,
        channel_id=order.channel_id,
        business_date=today,
        source="pos",
        status="posted",
        subtotal=t.gross,
        discount=t.discount,
        service_charge=t.taxed.service_charge,
        tax=t.taxed.tax_total,
        total=t.taxed.total,
        tip=tip,
        rounding=rounding,
        cost=0,
        note=order.note,
        created_by=user_id,
    )
    db.add(doc)
    await db.flush()
    return doc


async def _post_lines(
    db: AsyncSession, doc: SalesDocument, lines: list[PosLineOut], used: dict[uuid.UUID, uuid.UUID]
) -> None:
    for ln in lines:
        row = SalesLine(
            tenant_id=doc.tenant_id,
            document_id=doc.id,
            item_id=ln.item_id,
            qty=ln.qty,
            unit_price=ln.unit_price,
            bom_id=used.get(ln.item_id),
        )
        db.add(row)
        await db.flush()
        db.add_all(
            SalesModifierLine(
                tenant_id=doc.tenant_id,
                line_id=row.id,
                option_id=m.option_id,
                name=m.name,
                price_delta=m.price_delta,
            )
            for m in ln.modifiers
        )
    await db.flush()


async def pay(
    db: AsyncSession,
    order: PosOrder,
    *,
    user_id: uuid.UUID,
    data: PosPayIn,
    language: str,
) -> tuple[SalesDocument, list[Payment]]:
    require_open(order)
    pos = cast(PosSettings, await settings.get_setting(db, order.tenant_id, "pos"))
    if data.tip and not pos.tips_enabled:
        raise ConflictError("tips_disabled")
    shift = await current_shift(db, order.outlet_id, user_id)
    if shift is None and pos.require_shift:
        raise ConflictError("shift_required")
    lines = [ln for ln in await lines_of(db, order, language) if ln.status != "void"]
    if not lines:
        raise ConflictError("order_empty")
    methods = await _methods(db, order.tenant_id)
    t = await totals(db, order, lines)
    all_cash = all(
        methods.get(p.method) and methods[p.method].kind == "cash" for p in data.payments
    )
    total = t.taxed.total
    rounding = cash_rounding(total, pos.cash_rounding_step) if all_cash else 0
    tenders = _tenders(data.payments, methods, total + rounding + data.tip)
    doc = await _post_document(db, order, user_id, t, data.tip, rounding)
    rows = list(
        await db.scalars(
            select(PosOrderLine).where(
                PosOrderLine.order_id == order.id, PosOrderLine.status != "void"
            )
        )
    )
    await discounts.recheck(db, order, rows, lines)
    qty = stock_quantities(rows, await option_changes(db, rows))
    used = await consume_for_sale(db, doc, qty, user_id, DOC)
    await _post_lines(db, doc, lines, used)
    payments = [
        Payment(
            tenant_id=order.tenant_id,
            order_id=order.id,
            document_id=doc.id,
            shift_id=shift.id if shift else None,
            method_code=pay_in.method,
            kind=method.kind,
            amount=pay_in.amount,
            tendered=pay_in.tendered,
            change=change,
            reference=pay_in.reference,
            created_by=user_id,
        )
        for pay_in, method, change in tenders
    ]
    db.add_all(payments)
    now = datetime.now(UTC)
    await mark_sent(db, order, rows, user_id)  # paid before it was sent: still made
    order.status, order.document_id, order.paid_at, order.paid_by = "paid", doc.id, now, user_id
    order.shift_id = shift.id if shift else None
    await db.flush()
    await _audit(db, order, user_id, "pay", {"total": doc.total, "tip": data.tip})
    await announce(db, order, user_id, ORDER_PAID)
    return doc, payments
