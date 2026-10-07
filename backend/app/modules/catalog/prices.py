"""Channels and channel list prices (FR-CAT-004, docs/09 0.20).

A price applies from its `valid_from` date until a later start date replaces it. Promotions are
discounts on the sale, not prices. Past prices are history used by margin reports (slice 1k),
so only prices that have not started yet can be deleted; a typo is fixed by saving the same
start date again (audited with before and after).
"""

import uuid
from datetime import date
from typing import Any, cast

from sqlalchemy import ColumnElement, Date, Select, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tenant
from app.core.pagination import PageParams, paginate
from app.modules.catalog.models import Channel, Item, ItemPrice
from app.modules.catalog.schemas import ChannelIn, EffectivePrice, PriceIn, PriceOut
from app.modules.catalog.service import InvalidCatalogReference

HISTORY_LIMIT = 500  # per item; years of weekly price changes on every channel


# ─── Channels ─────────────────────────────────────────────────────────────


async def list_channels(db: AsyncSession, *, include_inactive: bool = False) -> list[Channel]:
    stmt = select(Channel).order_by(Channel.sort_order, Channel.name)
    if not include_inactive:
        stmt = stmt.where(Channel.is_active)
    return list((await db.execute(stmt)).scalars())


async def save_channel(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ChannelIn,
    channel_id: uuid.UUID | None = None,
) -> Channel:
    if channel_id is None:
        row = Channel(tenant_id=tenant_id, **data.model_dump())
        db.add(row)
        action, before = "catalog.channel.create", None
    else:
        found = await db.get(Channel, channel_id, with_for_update=True)
        if found is None:
            raise NotFoundError("channel_not_found")
        if found.code != data.code:
            # Settings (service charge per channel) and later sales refer to the code.
            raise ConflictError("channel_code_locked")
        row = found
        before = ChannelIn.model_validate(row, from_attributes=True).model_dump()
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        action = "catalog.channel.update"
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("channel_code_taken") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        target_type="channel",
        target_id=row.id,
        summary={"before": before, "after": data.model_dump()},
    )
    return row


# ─── Prices ───────────────────────────────────────────────────────────────


async def tenant_today(db: AsyncSession, tenant_id: uuid.UUID) -> date:
    """Today's date where the tenant is (PostgreSQL's time zone data, no extra dependency)."""
    today = func.timezone(Tenant.timezone, func.now())
    return cast(date, await db.scalar(select(sql_cast(today, Date)).where(Tenant.id == tenant_id)))


def _price_out(row: ItemPrice) -> PriceOut:
    return PriceOut(
        id=row.id,
        item_id=row.item_id,
        channel_id=row.channel_id,
        valid_from=row.valid_from,
        price=row.price,
    )


async def _visible_channel(db: AsyncSession, channel_id: uuid.UUID) -> Channel:
    # Foreign keys ignore RLS: look the channel up under RLS so another tenant's id is refused.
    channel = await db.get(Channel, channel_id)
    if channel is None:
        raise InvalidCatalogReference(details={"channel_id": str(channel_id)})
    return channel


async def price_history(db: AsyncSession, item_id: uuid.UUID) -> list[PriceOut]:
    if await db.get(Item, item_id) is None:
        raise NotFoundError("item_not_found")
    stmt = (
        select(ItemPrice)
        .where(ItemPrice.item_id == item_id, ItemPrice.outlet_id.is_(None))
        .order_by(ItemPrice.valid_from.desc(), ItemPrice.channel_id)
        .limit(HISTORY_LIMIT)
    )
    return [_price_out(r) for r in (await db.execute(stmt)).scalars()]


async def set_price(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    data: PriceIn,
) -> PriceOut:
    """Create the price starting on `valid_from`, or correct the one that already starts then."""
    if await db.get(Item, item_id) is None:
        raise NotFoundError("item_not_found")
    await _visible_channel(db, data.channel_id)
    row = await db.scalar(
        select(ItemPrice)
        .where(
            ItemPrice.item_id == item_id,
            ItemPrice.channel_id == data.channel_id,
            ItemPrice.outlet_id.is_(None),
            ItemPrice.valid_from == data.valid_from,
        )
        .with_for_update()
    )
    before = None if row is None else row.price
    if row is None:
        row = ItemPrice(
            tenant_id=tenant_id, item_id=item_id, created_by=user_id, **data.model_dump()
        )
        db.add(row)
    else:
        row.price = data.price
    try:
        await db.flush()
    except IntegrityError:
        # Two people added the same start date at once; the client reloads and retries.
        raise ConflictError("price_conflict") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.price.create" if before is None else "catalog.price.update",
        target_type="item",
        target_id=item_id,
        summary={
            "channel_id": str(data.channel_id),
            "valid_from": data.valid_from.isoformat(),
            "before": before,
            "after": data.price,
        },
    )
    return _price_out(row)


async def delete_price(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, price_id: uuid.UUID
) -> None:
    row = await db.get(ItemPrice, price_id, with_for_update=True)
    if row is None:
        raise NotFoundError("price_not_found")
    if row.valid_from <= await tenant_today(db, tenant_id):
        raise ConflictError("price_already_started")
    await db.delete(row)
    await db.flush()
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="catalog.price.delete",
        target_type="item",
        target_id=row.item_id,
        summary={
            "channel_id": str(row.channel_id),
            "valid_from": row.valid_from.isoformat(),
            "price": row.price,
        },
    )


async def effective_prices(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    on: date | None,
    params: PageParams,
) -> tuple[list[EffectivePrice], str | None]:
    """The price list of a channel on a date (default: today): one row per active item."""
    await _visible_channel(db, channel_id)
    day = on or await tenant_today(db, tenant_id)
    # DISTINCT ON keeps the first row per item in ORDER BY order: the latest start date.
    latest = (
        select(ItemPrice.item_id, ItemPrice.valid_from, ItemPrice.price)
        .where(
            ItemPrice.channel_id == channel_id,
            ItemPrice.outlet_id.is_(None),
            ItemPrice.valid_from <= day,
            or_(ItemPrice.valid_to.is_(None), ItemPrice.valid_to >= day),
        )
        .order_by(ItemPrice.item_id, ItemPrice.valid_from.desc())
        .ext(distinct_on(ItemPrice.item_id))
        .subquery()
    )
    stmt = (
        select(latest.c.item_id, latest.c.valid_from, latest.c.price)
        .join(Item, Item.id == latest.c.item_id)
        .where(Item.is_active)
    )
    item_id = cast(ColumnElement[Any], latest.c.item_id)
    rows, cursor = await paginate(
        db,
        cast(Select[Any], stmt),
        params,
        id_column=item_id,
        sortable={"item_id": item_id},
        default_sort="item_id",
    )
    return [EffectivePrice(item_id=i, valid_from=v, price=p) for i, v, p in rows], cursor
