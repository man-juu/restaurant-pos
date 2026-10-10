"""Stock alerts (FR-INV-012, docs/05 rule 8): negative stock, below reorder point, batch near
expiry and expired stock on hand. Run by the alerts job per tenant; each scan reports what is
true now and the core opens or resolves alerts to match."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant
from app.core.notifications.service import Condition, sync
from app.core.settings import service as settings
from app.core.settings.schemas import StockSettings
from app.modules.catalog.interface import item_names, stock_items, tenant_today
from app.modules.inventory import planning
from app.modules.inventory.models import StockBalance, StockBatch, StockLevel

LINK = "/inventory"


def _num(q: Decimal) -> str:
    return f"{q.normalize():f}"


async def _on_hand(db: AsyncSession) -> dict[tuple[uuid.UUID, uuid.UUID], Decimal]:
    stmt = select(
        StockBalance.outlet_id, StockBalance.item_id, func.sum(StockBalance.qty)
    ).group_by(StockBalance.outlet_id, StockBalance.item_id)
    return {(o, i): q for o, i, q in (await db.execute(stmt)).all()}


async def _negative(
    db: AsyncSession, have: dict[tuple[uuid.UUID, uuid.UUID], Decimal]
) -> list[tuple[uuid.UUID, uuid.UUID, Decimal]]:
    rows = [(o, i, q) for (o, i), q in have.items() if q < 0]
    items = await stock_items(db, {i for _, i, _ in rows})
    # Estimated items (rice, oil) never raise negative-stock alerts (docs/05 items).
    return [r for r in rows if r[1] in items and not items[r[1]].estimated]


async def _below_reorder(
    db: AsyncSession, have: dict[tuple[uuid.UUID, uuid.UUID], Decimal]
) -> list[tuple[uuid.UUID, uuid.UUID, Decimal, Decimal]]:
    stmt = select(StockLevel.outlet_id, StockLevel.item_id, StockLevel.reorder_point).where(
        StockLevel.reorder_point.is_not(None)
    )
    out = []
    for o, i, point in (await db.execute(stmt)).all():
        q = have.get((o, i), Decimal(0))
        if point is not None and q <= point:
            out.append((o, i, q, point))
    return out


async def _batches(
    db: AsyncSession, until: date
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, Decimal, date]]:
    stmt = (
        select(
            StockBalance.outlet_id,
            StockBalance.item_id,
            StockBatch.id,
            StockBalance.qty,
            StockBatch.expiry_date,
        )
        .join(StockBatch, StockBatch.id == StockBalance.batch_id)
        .where(
            StockBalance.qty > 0,
            StockBatch.expiry_date.is_not(None),
            StockBatch.expiry_date <= until,
        )
    )
    rows = (await db.execute(stmt)).all()
    return [(o, i, b, q, e) for o, i, b, q, e in rows if e is not None]


async def _low_days(
    db: AsyncSession, have: dict[tuple[uuid.UUID, uuid.UUID], Decimal], today: date, limit: int
) -> list[tuple[uuid.UUID, uuid.UUID, Decimal, Decimal]]:
    """FR-INV-011/012: stock that lasts fewer than `limit` days at the recent pace."""
    if limit <= 0:
        return []
    out = []
    for outlet in {o for o, _ in have}:
        ids = {i for o, i in have if o == outlet}
        usage = await planning.weekday_usage(db, outlet, ids, today)
        for item, week in usage.items():
            left = planning.days_left(have[(outlet, item)], week, today)
            if left is not None and 0 < left < limit:
                out.append((outlet, item, have[(outlet, item)], left))
    return out


async def scan_stock(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    stock = cast(StockSettings, await settings.get_setting(db, tenant_id, "stock"))
    today = await tenant_today(db, tenant_id)
    have = await _on_hand(db)
    negative = await _negative(db, have)
    low = await _below_reorder(db, have)
    dated = await _batches(db, today + timedelta(days=stock.expiry_warning_days))
    short = await _low_days(db, have, today, stock.low_days_alert)
    ids = {r[1] for r in negative} | {r[1] for r in low} | {r[1] for r in dated}
    ids |= {r[1] for r in short}
    language = await db.scalar(select(Tenant.language).where(Tenant.id == tenant_id)) or "en"
    names = await item_names(db, tenant_id, language, ids)

    def info(item: uuid.UUID, **more: str) -> dict[str, str]:
        label = names.get(item)
        return {
            "item": label.name if label else str(item),
            "unit": label.unit_code if label else "",
            **more,
        }

    await sync(
        db,
        tenant_id,
        "negative_stock",
        [Condition(o, i, details=info(i, qty=_num(q)), link=LINK) for o, i, q in negative],
    )
    await sync(
        db,
        tenant_id,
        "below_reorder_point",
        [
            Condition(o, i, details=info(i, qty=_num(q), point=_num(p)), link=LINK)
            for o, i, q, p in low
        ],
    )
    await sync(
        db,
        tenant_id,
        "batch_near_expiry",
        [
            Condition(o, i, b, info(i, qty=_num(q), expiry=e.isoformat()), LINK)
            for o, i, b, q, e in dated
            if e >= today
        ],
    )
    await sync(
        db,
        tenant_id,
        "expired_stock",
        [
            Condition(o, i, b, info(i, qty=_num(q), expiry=e.isoformat()), LINK)
            for o, i, b, q, e in dated
            if e < today
        ],
    )
    await sync(
        db,
        tenant_id,
        "low_days_of_inventory",
        [
            Condition(o, i, details=info(i, qty=_num(q), days=_num(d)), link=LINK)
            for o, i, q, d in short
        ],
    )
