"""I-3: what a completed production consumed is what its output was valued at (within one
minor unit of rounding per order)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.models import ProductionOrder


async def output_value_matches_input(db: AsyncSession) -> int:
    output_value = func.round(ProductionOrder.actual_qty * ProductionOrder.unit_cost)
    stmt = (
        select(func.count())
        .select_from(ProductionOrder)
        .where(
            ProductionOrder.status == "completed",
            func.abs(output_value - ProductionOrder.input_value) > 1,
        )
    )
    return int(await db.scalar(stmt) or 0)
