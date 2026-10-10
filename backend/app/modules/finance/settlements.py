"""Delivery-platform settlements (FR-FIN-007). Sales were journaled gross against the
platform receivable (ADR 0.63); a settlement clears it: Dr the bank (payout), Dr platform
commission (commission and fees, net of adjustments), Cr platform receivable (gross)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.reports import Period
from app.core.settings import service as settings
from app.modules.catalog.interface import channel_kind
from app.modules.finance import auto, ledger
from app.modules.finance.models import MoneyAccount
from app.modules.finance.settlement_models import PlatformSettlement
from app.modules.finance.settlement_schemas import ReconcileOut, SettlementIn
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.interface import channel_total

SOURCE = "platform_settlement"


async def _audit(db: AsyncSession, row: PlatformSettlement, user_id: uuid.UUID, act: str) -> None:
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=user_id,
        outlet_id=row.outlet_id,
        action=f"finance.settlement.{act}",
        target_type="platform_settlement",
        target_id=row.id,
        summary={"number": row.number, "gross": row.gross, "payout": row.payout},
    )


async def _journal(db: AsyncSession, row: PlatformSettlement, account: MoneyAccount) -> None:
    if not await auto.ready(db, row.tenant_id, row.paid_on):
        return
    roles = await auto.account_roles(db)
    cost = row.gross - row.payout  # commission + fees - adjustments
    bank = roles[auto.MONEY_ROLES.get(account.kind, "bank")]
    lines = [
        ledger.Line(bank, debit=row.payout, outlet_id=row.outlet_id),
        ledger.Line(roles["platform_receivable"], credit=row.gross, outlet_id=row.outlet_id),
    ]
    if cost:
        fee = roles["platform_commission"]
        lines.append(ledger.Line(fee, max(cost, 0), max(-cost, 0), row.outlet_id))
    lines = [ln for ln in lines if ln.debit or ln.credit]
    if lines:
        head = ledger.Head(row.paid_on, SOURCE, row.id, row.number, row.outlet_id)
        await ledger.write(
            db, tenant_id=row.tenant_id, user_id=row.created_by, head=head, lines=lines
        )


async def create(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: SettlementIn
) -> PlatformSettlement:
    await visible_outlet(db, data.outlet_id)
    if await channel_kind(db, data.channel_id) != "platform":
        raise ConflictError("not_a_platform_channel")
    account = await db.get(MoneyAccount, data.account_id)
    if account is None or not account.is_active:
        raise NotFoundError("account_not_found")
    number = await settings.allocate_number(
        db, tenant_id=tenant_id, doc_type=SOURCE, on=data.paid_on
    )
    row = PlatformSettlement(
        tenant_id=tenant_id, number=number, created_by=user_id, **data.model_dump()
    )
    db.add(row)
    await db.flush()
    await _audit(db, row, user_id, "create")
    await _journal(db, row, account)
    return row


async def get(db: AsyncSession, settlement_id: uuid.UUID) -> PlatformSettlement:
    row = await db.get(PlatformSettlement, settlement_id, with_for_update=True)
    if row is None:
        raise NotFoundError("settlement_not_found")
    return row


async def reverse(db: AsyncSession, row: PlatformSettlement, user_id: uuid.UUID) -> None:
    if row.status != "posted":
        raise ConflictError("wrong_status", details={"status": row.status})
    row.status, row.reversed_by, row.reversed_at = "reversed", user_id, datetime.now(UTC)
    await db.flush()
    await _audit(db, row, user_id, "reverse")
    await auto.reverse_own(db, row.tenant_id, user_id, SOURCE, row.id)


async def payouts_by_account(db: AsyncSession) -> dict[uuid.UUID, int]:
    """Money that arrived in each account from platform payouts (account balances)."""
    rows = await db.execute(
        select(PlatformSettlement.account_id, func.sum(PlatformSettlement.payout))
        .where(PlatformSettlement.status == "posted")
        .group_by(PlatformSettlement.account_id)
    )
    return {a: int(v) for a, v in rows.all()}


async def reconcile(db: AsyncSession, period: Period, channel_id: uuid.UUID) -> ReconcileOut:
    """Booked platform sales against the settlements whose period starts in the range."""
    if period.outlet_id is None:
        raise ConflictError("outlet_required")
    orders, booked = await channel_total(db, period, channel_id, period.outlet_id)
    s = PlatformSettlement
    sums = (
        await db.execute(
            select(
                func.count(s.id),
                *(func.coalesce(func.sum(c), 0) for c in (s.gross, s.commission, s.fees)),
                func.coalesce(func.sum(s.adjustments), 0),
                func.coalesce(func.sum(s.payout), 0),
            ).where(
                s.status == "posted",
                s.channel_id == channel_id,
                s.outlet_id == period.outlet_id,
                s.period_from >= period.date_from,
                s.period_from <= period.date_to,
            )
        )
    ).one()
    count, gross, commission, fees, adjustments, payout = (int(v) for v in sums)
    pct = f"{Decimal(commission + fees) * 100 / gross:.1f}" if gross else None
    return ReconcileOut(
        orders=orders,
        booked_gross=booked,
        settled_gross=gross,
        difference=booked - gross,
        commission=commission,
        fees=fees,
        adjustments=adjustments,
        payout=payout,
        commission_pct=pct,
        settlements=count,
    )
