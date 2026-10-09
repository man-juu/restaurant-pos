"""Stock targets per outlet and item (docs/05 2.3). Par levels feed the daily prep list
(FR-PRD-008); min, reorder point and max feed alerts and reorder hints (slice 1j)."""

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import NotFoundError
from app.modules.catalog.interface import item_names, stock_items
from app.modules.inventory.models import StockBalance, StockLevel
from app.modules.inventory.opening import visible_outlet
from app.modules.inventory.schemas import LevelIn, LevelOut, LevelsIn

TARGETS = ("par_qty", "min_qty", "reorder_point", "max_qty", "safety_qty", "lead_time_days")


async def on_hand_by_item(
    db: AsyncSession, outlet_id: uuid.UUID, item_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    stmt = (
        select(StockBalance.item_id, func.sum(StockBalance.qty))
        .where(StockBalance.outlet_id == outlet_id, StockBalance.item_id.in_(item_ids))
        .group_by(StockBalance.item_id)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def list_levels(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, language: str
) -> list[LevelOut]:
    rows = list(await db.scalars(select(StockLevel).where(StockLevel.outlet_id == outlet_id)))
    ids = {r.item_id for r in rows}
    names = await item_names(db, tenant_id, language, ids)
    have = await on_hand_by_item(db, outlet_id, ids)
    out = [
        LevelOut(
            item_id=r.item_id,
            **{k: getattr(r, k) for k in TARGETS},
            sku=names[r.item_id].sku,
            name=names[r.item_id].name,
            unit_code=names[r.item_id].unit_code,
            on_hand=have.get(r.item_id, Decimal(0)),
        )
        for r in rows
    ]
    return sorted(out, key=lambda x: x.name.lower())


def _empty(level: LevelIn) -> bool:
    return all(getattr(level, k) is None for k in TARGETS)


async def save_levels(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: LevelsIn
) -> None:
    """Upsert each item's targets; an item with no targets left is removed."""
    await visible_outlet(db, data.outlet_id)
    ids = {lv.item_id for lv in data.levels}
    items = await stock_items(db, ids)
    if bad := {i for i in ids if i not in items or not items[i].is_stocked}:
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, bad))})
    gone = [lv.item_id for lv in data.levels if _empty(lv)]
    if gone:
        await db.execute(
            delete(StockLevel).where(
                StockLevel.outlet_id == data.outlet_id, StockLevel.item_id.in_(gone)
            )
        )
    keep = [lv for lv in data.levels if not _empty(lv)]
    if keep:
        stmt = insert(StockLevel).values(
            [
                {"tenant_id": tenant_id, "outlet_id": data.outlet_id, **lv.model_dump()}
                for lv in keep
            ]
        )
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["tenant_id", "outlet_id", "item_id"],
                set_={k: stmt.excluded[k] for k in TARGETS},
            )
        )
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=data.outlet_id,
        action="inventory.levels.save",
        target_type="outlet",
        target_id=data.outlet_id,
        summary={"saved": len(keep), "removed": len(gone)},
    )


async def par_and_on_hand(
    db: AsyncSession, outlet_id: uuid.UUID, also: set[uuid.UUID] | None = None
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """Items with a par level at the outlet, plus `also`: item -> (par or 0, on hand)."""
    rows = (
        await db.execute(
            select(StockLevel.item_id, StockLevel.par_qty).where(
                StockLevel.outlet_id == outlet_id, StockLevel.par_qty > 0
            )
        )
    ).all()
    pars = {i: par or Decimal(0) for i, par in rows}
    ids = set(pars) | (also or set())
    have = await on_hand_by_item(db, outlet_id, ids)
    return {i: (pars.get(i, Decimal(0)), have.get(i, Decimal(0))) for i in ids}


async def below_par(
    db: AsyncSession, outlet_id: uuid.UUID
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """Items under their par level at the outlet: item -> (par, on hand)."""
    levels = await par_and_on_hand(db, outlet_id)
    return {i: v for i, v in levels.items() if v[1] < v[0]}
