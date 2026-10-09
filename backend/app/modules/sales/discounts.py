"""Discounts on POS orders (FR-SAL-007): on a line or on the whole order, as a percentage
or an amount, always with a reason. Each role has a maximum percentage (docs/03 rule 7,
default cashier 10 %, manager 50 %, owner none); a bigger discount needs someone whose limit
covers it. Amount discounts are checked as the percentage of what they discount."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.approvals import ensure_within_limit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings.pricing import round_half_up_div
from app.modules.sales.models import PosOrder, PosOrderLine
from app.modules.sales.pos_schemas import DiscountIn

FULL = 10_000  # basis points in 100 %


def discount_amount(base: int, kind: str | None, value: int | None) -> int:
    """The discount on `base`, rounded half up once (docs/05 rule 3), never above it."""
    if kind is None or value is None or base <= 0:
        return 0
    if kind == "percent":
        return min(base, round_half_up_div(base * value, FULL))
    return min(base, value)


def as_percent_bp(base: int, kind: str, value: int) -> int:
    """What the discount is worth as basis points of `base`, rounded up so an amount just
    over the limit is never let through."""
    if kind == "percent":
        return value
    return -(-value * FULL // base) if base > 0 else FULL


def check(base: int, data: DiscountIn, limit: int | None) -> None:
    if data.kind == "percent" and data.value > FULL:
        raise ConflictError("discount_too_large")
    if data.kind == "amount" and data.value > base:
        raise ConflictError("discount_too_large", details={"max": base})
    ensure_within_limit(as_percent_bp(base, data.kind, data.value), limit, what="discount")


def apply(row: PosOrder | PosOrderLine, data: DiscountIn | None, user_id: uuid.UUID) -> None:
    row.discount_kind = data.kind if data else None
    row.discount_value = data.value if data else None
    row.discount_reason = data.reason if data else None
    row.discount_by = user_id if data else None


async def open_line(db: AsyncSession, order: PosOrder, line_id: uuid.UUID) -> PosOrderLine:
    line = await db.get(PosOrderLine, line_id)
    if line is None or line.order_id != order.id or line.status == "void":
        raise NotFoundError("line_not_found")
    return line
