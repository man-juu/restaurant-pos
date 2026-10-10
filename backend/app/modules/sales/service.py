"""Manual daily sales (FR-SAL-002, 003): per outlet, day and channel, the quantities sold.
Saving posts a sales document and takes the recipes' ingredients out of stock in the same
transaction; saving again replaces it (the earlier stock comes back first). A locked day
takes no entries until someone with the lock permission reopens it."""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.pricing import calculate
from app.core.settings.schemas import ServiceChargeSettings, TaxSettings
from app.modules.catalog.interface import (
    channel_code,
    consumption,
    item_ids_by_code,
    prices_on,
    stock_items,
)
from app.modules.inventory.interface import (
    OutLine,
    Posting,
    consume,
    negative_allowed,
    reverse,
    visible_outlet,
)
from app.modules.sales import doc_events
from app.modules.sales.models import SalesDay, SalesDocument, SalesLine
from app.modules.sales.schemas import DayEntryIn, EntryLine

DOC = "sales_day"


async def get_day(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, on: date, *, lock: bool = False
) -> SalesDay:
    stmt = select(SalesDay).where(SalesDay.outlet_id == outlet_id, SalesDay.business_date == on)
    day = await db.scalar(stmt.with_for_update() if lock else stmt)
    if day is None:
        day = SalesDay(tenant_id=tenant_id, outlet_id=outlet_id, business_date=on, status="open")
        db.add(day)
        await db.flush()
    return day


async def _resolve(
    db: AsyncSession, channel_id: uuid.UUID, lines: list[EntryLine]
) -> list[tuple[uuid.UUID, EntryLine]]:
    codes = {ln.platform_code for ln in lines if ln.platform_code}
    mapped = await item_ids_by_code(db, channel_id, codes) if codes else {}
    if unknown := codes - mapped.keys():
        raise NotFoundError("unknown_platform_code", details={"codes": sorted(unknown)})
    out = [(ln.item_id or mapped[cast(str, ln.platform_code)], ln) for ln in lines]
    items = await stock_items(db, {i for i, _ in out})
    if bad := {i for i, _ in out if i not in items or not items[i].is_active}:
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, bad))})
    return out


def _money(qty: Decimal, price: int) -> int:
    return int((qty * price).quantize(Decimal(1), ROUND_HALF_UP))


async def _prices(
    db: AsyncSession, data: DayEntryIn, rows: list[tuple[uuid.UUID, EntryLine]]
) -> list[int]:
    want = {i for i, ln in rows if ln.unit_price is None}
    listed = (
        await prices_on(db, data.channel_id, want, data.business_date, data.outlet_id)
        if want
        else {}
    )
    if missing := want - listed.keys():
        raise ConflictError("price_missing", details={"item_ids": sorted(map(str, missing))})
    return [ln.unit_price if ln.unit_price is not None else listed[i] for i, ln in rows]


async def _replace_previous(db: AsyncSession, data: DayEntryIn, user_id: uuid.UUID) -> None:
    stmt = select(SalesDocument).where(
        SalesDocument.outlet_id == data.outlet_id,
        SalesDocument.channel_id == data.channel_id,
        SalesDocument.business_date == data.business_date,
        SalesDocument.source == "manual_day",
        SalesDocument.status == "posted",
    )
    old = await db.scalar(stmt.with_for_update())
    if old is None:
        return
    p = Posting(old.tenant_id, old.outlet_id, user_id, DOC, old.id, old.business_date)
    try:
        await reverse(db, p, DOC, old.id)
    except ConflictError as err:  # untracked items only: no stock was taken
        if err.code != "nothing_to_reverse":
            raise
    old.status = "replaced"
    await db.flush()
    await doc_events.reversed_(db, old, user_id)


async def take_stock(
    db: AsyncSession,
    p: Posting,
    qty: dict[uuid.UUID, Decimal],
    movement_type: str = "sale_consumption",
) -> tuple[int, dict[uuid.UUID, uuid.UUID]]:
    """Take the recipes' ingredients (and any extra stocked items in `qty`) out of stock.
    Returns (stock value taken, recipe version used per item)."""
    taken, used = await consumption(db, qty, p.business_date)
    items = await stock_items(db, taken.keys())
    outs = [OutLine(i, q) for i, q in taken.items() if i in items and items[i].is_stocked and q > 0]
    if not outs:
        return 0, used
    allowed = await negative_allowed(db, p.tenant_id, "sale", confirmed=True)
    result = await consume(db, p, movement_type, outs, allow_negative=allowed)
    return -sum(m.value for m in result.movements), used


async def consume_for_sale(
    db: AsyncSession,
    doc: SalesDocument,
    qty: dict[uuid.UUID, Decimal],
    user_id: uuid.UUID,
    doc_type: str = DOC,
) -> dict[uuid.UUID, uuid.UUID]:
    """Stock out for a posted sale; sets the document's cost."""
    p = Posting(doc.tenant_id, doc.outlet_id, user_id, doc_type, doc.id, doc.business_date)
    cost, used = await take_stock(db, p, qty)
    doc.cost = cost
    return used


async def enter_day(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: DayEntryIn
) -> SalesDocument:
    await visible_outlet(db, data.outlet_id)
    day = await get_day(db, tenant_id, data.outlet_id, data.business_date, lock=True)
    if day.status == "locked":
        raise ConflictError("day_locked")
    code = await channel_code(db, data.channel_id)
    rows = await _resolve(db, data.channel_id, data.lines)
    prices = await _prices(db, data, rows)
    subtotal = sum(_money(ln.qty, price) for (_, ln), price in zip(rows, prices, strict=True))
    reported = data.reported_total
    if reported is not None and reported > subtotal:
        raise ConflictError("reported_above_list", details={"subtotal": subtotal})
    discount = subtotal - reported if reported is not None else 0
    tax = cast(TaxSettings, await settings.get_setting(db, tenant_id, "tax"))
    sc = cast(ServiceChargeSettings, await settings.get_setting(db, tenant_id, "service_charge"))
    totals = calculate(
        [subtotal - discount], tax=tax, service_charge=sc, channel=code, outlet_id=data.outlet_id
    )
    # Lock order for every posting: number counter first, then stock rows. Taking the
    # counter after reversing old stock let two entries deadlock (found by the load test).
    number = await settings.allocate_number(
        db, tenant_id=tenant_id, doc_type=DOC, on=data.business_date
    )
    await _replace_previous(db, data, user_id)
    doc = SalesDocument(
        tenant_id=tenant_id,
        number=number,
        outlet_id=data.outlet_id,
        channel_id=data.channel_id,
        business_date=data.business_date,
        source="manual_day",
        status="posted",
        subtotal=subtotal,
        discount=discount,
        service_charge=totals.service_charge,
        tax=totals.tax_total,
        total=totals.total,
        cost=0,
        note=data.note,
        created_by=user_id,
    )
    db.add(doc)
    await db.flush()
    qty: dict[uuid.UUID, Decimal] = {}
    for item_id, ln in rows:
        qty[item_id] = qty.get(item_id, Decimal(0)) + ln.qty
    used = await consume_for_sale(db, doc, qty, user_id)
    db.add_all(
        SalesLine(
            tenant_id=tenant_id,
            document_id=doc.id,
            item_id=item_id,
            qty=ln.qty,
            unit_price=price,
            platform_code=ln.platform_code,
            bom_id=used.get(item_id),
        )
        for (item_id, ln), price in zip(rows, prices, strict=True)
    )
    await db.flush()
    await _audit(db, doc, user_id, "enter")
    await doc_events.posted(db, doc, user_id)
    return doc


async def _audit(db: AsyncSession, doc: SalesDocument, user_id: uuid.UUID, action: str) -> None:
    await audit.record(
        db,
        tenant_id=doc.tenant_id,
        user_id=user_id,
        outlet_id=doc.outlet_id,
        action=f"sales.day.{action}",
        target_type="sales_document",
        target_id=doc.id,
        summary={"number": doc.number, "total": doc.total, "date": doc.business_date.isoformat()},
    )


async def set_lock(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    outlet_id: uuid.UUID,
    on: date,
    locked: bool,
) -> SalesDay:
    """FR-SAL-003: lock after review; reopening is a separate, audited decision."""
    await visible_outlet(db, outlet_id)
    day = await get_day(db, tenant_id, outlet_id, on, lock=True)
    if (day.status == "locked") == locked:
        raise ConflictError("wrong_status", details={"status": day.status})
    day.status = "locked" if locked else "open"
    day.locked_by, day.locked_at = (user_id, datetime.now(UTC)) if locked else (None, None)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=outlet_id,
        action="sales.day.lock" if locked else "sales.day.reopen",
        target_type="sales_day",
        target_id=day.id,
        summary={"date": on.isoformat()},
    )
    return day
