"""Cash shifts (FR-SAL-009): a cashier opens a drawer with a float, records cash put in or
taken out, and closes with a count. Expected cash = float + cash kept from sales + cash in -
cash out; the variance is counted - expected. Closing freezes the figures."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.models import User
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.models import CashMovement, CashShift, Payment, PosOrder
from app.modules.sales.pos_schemas import (
    MovementIn,
    MovementOut,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftOut,
)


async def current_shift(
    db: AsyncSession, outlet_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> CashShift | None:
    stmt = select(CashShift).where(
        CashShift.outlet_id == outlet_id,
        CashShift.cashier_id == user_id,
        CashShift.status == "open",
    )
    return cast(CashShift | None, await db.scalar(stmt.with_for_update() if lock else stmt))


async def get_shift(db: AsyncSession, shift_id: uuid.UUID, *, lock: bool = False) -> CashShift:
    shift = await db.get(CashShift, shift_id, with_for_update=lock)
    if shift is None:
        raise NotFoundError("shift_not_found")
    return shift


async def open_shift(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: ShiftOpenIn
) -> CashShift:
    await visible_outlet(db, data.outlet_id)
    shift = CashShift(
        tenant_id=tenant_id,
        outlet_id=data.outlet_id,
        cashier_id=user_id,
        status="open",
        opening_float=data.opening_float,
    )
    db.add(shift)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("shift_already_open") from None
    await _audit(db, shift, user_id, "open", {"float": data.opening_float})
    return shift


def _require_open(shift: CashShift) -> None:
    if shift.status != "open":
        raise ConflictError("wrong_status", details={"status": shift.status})


async def add_movement(
    db: AsyncSession, shift: CashShift, *, user_id: uuid.UUID, data: MovementIn
) -> None:
    _require_open(shift)
    db.add(
        CashMovement(
            tenant_id=shift.tenant_id,
            shift_id=shift.id,
            kind=data.kind,
            amount=data.amount,
            reason=data.reason,
            created_by=user_id,
        )
    )
    await db.flush()
    await _audit(db, shift, user_id, f"cash_{data.kind}", {"amount": data.amount})


async def _figures(db: AsyncSession, shift: CashShift) -> dict[str, object]:
    by_method = {
        code: int(total)
        for code, total in (
            await db.execute(
                select(Payment.method_code, func.sum(Payment.amount))
                .where(Payment.shift_id == shift.id)
                .group_by(Payment.method_code)
            )
        ).all()
    }
    cash_sales = int(
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.shift_id == shift.id, Payment.kind == "cash"
            )
        )
        or 0
    )
    moves = list(
        await db.scalars(
            select(CashMovement)
            .where(CashMovement.shift_id == shift.id)
            .order_by(CashMovement.created_at)
        )
    )
    cash_in = sum(m.amount for m in moves if m.kind == "in")
    cash_out = sum(m.amount for m in moves if m.kind == "out")
    orders = await db.scalar(
        select(func.count()).select_from(PosOrder).where(PosOrder.shift_id == shift.id)
    )
    return {
        "by_method": by_method,
        "cash_sales": cash_sales,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "expected": shift.opening_float + cash_sales + cash_in - cash_out,
        "orders": int(orders or 0),
        "movements": [
            MovementOut(kind=m.kind, amount=m.amount, reason=m.reason, created_at=m.created_at)
            for m in moves
        ],
    }


async def close_shift(
    db: AsyncSession, shift: CashShift, *, user_id: uuid.UUID, data: ShiftCloseIn
) -> None:
    _require_open(shift)
    figures = await _figures(db, shift)
    expected = cast(int, figures["expected"])
    shift.status, shift.closed_at, shift.closed_by = "closed", datetime.now(UTC), user_id
    shift.expected, shift.counted, shift.note = expected, data.counted, data.note
    await db.flush()
    await _audit(
        db,
        shift,
        user_id,
        "close",
        {"expected": expected, "counted": data.counted, "variance": data.counted - expected},
    )


async def shift_out(db: AsyncSession, shift: CashShift) -> ShiftOut:
    figures = await _figures(db, shift)
    name = await db.scalar(select(User.name).where(User.id == shift.cashier_id))
    # A closed shift reports the expected cash frozen at closing.
    expected = shift.expected if shift.expected is not None else cast(int, figures["expected"])
    return ShiftOut(
        id=shift.id,
        outlet_id=shift.outlet_id,
        cashier_id=shift.cashier_id,
        cashier_name=name or "",
        status=shift.status,  # type: ignore[arg-type]
        opening_float=shift.opening_float,
        opened_at=shift.opened_at,
        closed_at=shift.closed_at,
        cash_sales=cast(int, figures["cash_sales"]),
        cash_in=cast(int, figures["cash_in"]),
        cash_out=cast(int, figures["cash_out"]),
        expected=expected,
        counted=shift.counted,
        variance=None if shift.counted is None else shift.counted - expected,
        by_method=cast(dict[str, int], figures["by_method"]),
        orders=cast(int, figures["orders"]),
        note=shift.note,
        movements=cast(list[MovementOut], figures["movements"]),
    )


async def list_shifts(
    db: AsyncSession, outlet_id: uuid.UUID, date_from: date, date_to: date
) -> list[CashShift]:
    """Shifts opened in the period (UTC day bounds are close enough for a review list)."""
    start = datetime.combine(date_from, time.min, UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, UTC)
    stmt = (
        select(CashShift)
        .where(
            CashShift.outlet_id == outlet_id,
            CashShift.opened_at >= start,
            CashShift.opened_at < end,
        )
        .order_by(CashShift.opened_at.desc())
        .limit(200)
    )
    return list(await db.scalars(stmt))


async def _audit(
    db: AsyncSession, shift: CashShift, user_id: uuid.UUID, action: str, summary: dict[str, object]
) -> None:
    await audit.record(
        db,
        tenant_id=shift.tenant_id,
        user_id=user_id,
        outlet_id=shift.outlet_id,
        action=f"sales.shift.{action}",
        target_type="cash_shift",
        target_id=shift.id,
        summary=summary,
    )
