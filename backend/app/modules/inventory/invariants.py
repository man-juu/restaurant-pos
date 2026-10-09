"""I-1 (balances equal the sum of movements), I-2 (average cost never negative) and I-4
(a transfer that has arrived moved no quantity in total)."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import ItemCost, StockBalance, StockMovement


async def balances_match_movements(db: AsyncSession) -> int:
    moved = (
        select(
            StockMovement.outlet_id,
            StockMovement.item_id,
            StockMovement.batch_id,
            func.sum(StockMovement.qty).label("qty"),
        )
        .group_by(StockMovement.outlet_id, StockMovement.item_id, StockMovement.batch_id)
        .subquery()
    )
    same_key = and_(
        StockBalance.outlet_id == moved.c.outlet_id,
        StockBalance.item_id == moved.c.item_id,
        StockBalance.batch_id.is_not_distinct_from(moved.c.batch_id),
    )
    stmt = (
        select(func.count())
        .select_from(StockBalance)
        .join(moved, same_key, full=True)
        .where(func.coalesce(StockBalance.qty, 0) != func.coalesce(moved.c.qty, 0))
    )
    return int(await db.scalar(stmt) or 0)


async def average_not_negative(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(ItemCost).where(ItemCost.avg_cost < 0)
    return int(await db.scalar(stmt) or 0)


async def transfers_net_zero(db: AsyncSession) -> int:
    """Every document with stock in by transfer must net to zero across its transfer out
    and transfer in movements (losses on arrival are separate adjustments)."""
    arrived = select(StockMovement.doc_id).where(StockMovement.movement_type == "transfer_in")
    stmt = (
        select(StockMovement.doc_id)
        .where(
            StockMovement.doc_id.in_(arrived),
            StockMovement.movement_type.in_(("transfer_in", "transfer_out")),
        )
        .group_by(StockMovement.doc_id)
        .having(func.sum(StockMovement.qty) != 0)
    )
    return len((await db.execute(stmt)).all())
