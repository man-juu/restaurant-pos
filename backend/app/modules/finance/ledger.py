"""Posting to the general ledger (FR-FIN-002, 005, 009). The one place journal lines are
written: manual journals, the opening balance and (slice 3d) automatic journals all come
through `post`, so every entry is balanced, dated in an open period, on or after the books'
start date, and numbered."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.modules.finance.gl_models import (
    AccountingPeriod,
    GlAccount,
    JournalEntry,
    JournalLine,
    LedgerSetup,
)

DOC_TYPE = "journal"


@dataclass(frozen=True)
class Line:
    account_id: uuid.UUID
    debit: int = 0
    credit: int = 0
    outlet_id: uuid.UUID | None = None
    memo: str | None = None


async def setup_of(db: AsyncSession) -> LedgerSetup:
    row: LedgerSetup | None = await db.scalar(select(LedgerSetup))
    if row is None:
        raise ConflictError("ledger_not_set_up")
    return row


async def ensure_open(db: AsyncSession, tenant_id: uuid.UUID, on: date) -> None:
    """FR-FIN-005: the month of `on` must not be closed (rows are created as needed)."""
    await db.execute(
        insert(AccountingPeriod)
        .values(tenant_id=tenant_id, year=on.year, month=on.month)
        .on_conflict_do_nothing()
    )
    status = await db.scalar(
        select(AccountingPeriod.status).where(
            AccountingPeriod.year == on.year, AccountingPeriod.month == on.month
        )
    )
    if status == "closed":
        raise ConflictError("period_closed", details={"year": on.year, "month": on.month})


def _check_lines(lines: list[Line]) -> int:
    if len(lines) < 2:
        raise ConflictError("journal_needs_two_lines")
    for ln in lines:
        if ln.debit < 0 or ln.credit < 0 or (ln.debit == 0) == (ln.credit == 0):
            raise ConflictError("journal_line_one_side")
    debit, credit = sum(ln.debit for ln in lines), sum(ln.credit for ln in lines)
    if debit != credit:
        raise ConflictError("journal_not_balanced", details={"debit": debit, "credit": credit})
    return debit


async def _check_accounts(db: AsyncSession, lines: list[Line]) -> None:
    ids = {ln.account_id for ln in lines}
    found = set(
        await db.scalars(select(GlAccount.id).where(GlAccount.id.in_(ids), GlAccount.is_active))
    )
    if missing := ids - found:
        raise NotFoundError("account_not_found", details={"ids": sorted(map(str, missing))})


@dataclass(frozen=True)
class Head:
    entry_date: date
    source_doc_type: str
    source_doc_id: uuid.UUID | None = None
    memo: str | None = None
    outlet_id: uuid.UUID | None = None
    attachment_id: uuid.UUID | None = None


async def write(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    head: Head,
    lines: list[Line],
    status: str = "posted",
) -> JournalEntry:
    """Check and write an entry with its lines (status "submitted" waits for approval)."""
    total = _check_lines(lines)
    start = await setup_of(db)
    if head.entry_date < start.start_date and head.source_doc_type != "opening":
        raise ConflictError("before_books_start", details={"start": start.start_date.isoformat()})
    await ensure_open(db, tenant_id, head.entry_date)
    await _check_accounts(db, lines)
    entry = JournalEntry(
        tenant_id=tenant_id,
        number=await settings.allocate_number(
            db, tenant_id=tenant_id, doc_type=DOC_TYPE, on=head.entry_date
        ),
        outlet_id=head.outlet_id,
        entry_date=head.entry_date,
        memo=head.memo,
        source_doc_type=head.source_doc_type,
        source_doc_id=head.source_doc_id,
        attachment_id=head.attachment_id,
        status=status,
        total=total,
        created_by=user_id,
        submitted_at=datetime.now(UTC) if status == "submitted" else None,
    )
    db.add(entry)
    await db.flush()
    db.add_all(
        JournalLine(
            tenant_id=tenant_id,
            entry_id=entry.id,
            account_id=ln.account_id,
            outlet_id=ln.outlet_id or head.outlet_id,
            debit=ln.debit,
            credit=ln.credit,
            memo=ln.memo,
        )
        for ln in lines
    )
    await db.flush()
    return entry


async def entry_lines(db: AsyncSession, entry_id: uuid.UUID) -> list[JournalLine]:
    return list(await db.scalars(select(JournalLine).where(JournalLine.entry_id == entry_id)))


async def reverse(
    db: AsyncSession, entry: JournalEntry, *, user_id: uuid.UUID, on: date, memo: str | None
) -> JournalEntry:
    """A posted entry is never changed: the correction swaps debits and credits."""
    if entry.status != "posted":
        raise ConflictError("wrong_status", details={"status": entry.status})
    if await db.scalar(select(JournalEntry.id).where(JournalEntry.reverses_id == entry.id)):
        raise ConflictError("already_reversed")
    lines = [
        Line(ln.account_id, ln.credit, ln.debit, ln.outlet_id, ln.memo)
        for ln in await entry_lines(db, entry.id)
    ]
    head = Head(on, entry.source_doc_type, entry.source_doc_id, memo, entry.outlet_id)
    back = await write(db, tenant_id=entry.tenant_id, user_id=user_id, head=head, lines=lines)
    back.reverses_id = entry.id
    await db.flush()
    await audit.record(
        db,
        tenant_id=entry.tenant_id,
        user_id=user_id,
        action="finance.journal.reverse",
        target_type="journal_entry",
        target_id=entry.id,
        summary={"number": entry.number, "reversal": back.number},
    )
    return back


async def balances(
    db: AsyncSession, until: date, since: date | None = None
) -> dict[uuid.UUID, tuple[int, int]]:
    """Posted debits and credits per account, dated up to `until` (and from `since`)."""
    stmt = (
        select(JournalLine.account_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.status == "posted", JournalEntry.entry_date <= until)
        .group_by(JournalLine.account_id)
    )
    if since is not None:
        stmt = stmt.where(JournalEntry.entry_date >= since)
    return {a: (int(d), int(c)) for a, d, c in (await db.execute(stmt)).all()}


async def unbalanced_entries(db: AsyncSession) -> int:
    """Invariant I-5: posted entries whose debits and credits differ (must be 0)."""
    per_entry = (
        select(JournalLine.entry_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.status == "posted")
        .group_by(JournalLine.entry_id)
        .having(func.sum(JournalLine.debit) != func.sum(JournalLine.credit))
        .subquery()
    )
    return int(await db.scalar(select(func.count()).select_from(per_entry)) or 0)
