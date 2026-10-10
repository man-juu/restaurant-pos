"""Setting up the books, the chart of accounts, manual journals with approval and period
close (FR-FIN-002, 004, 005, 009)."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal
from app.core.approvals import approvers_needed, ensure_may_decide, mark_decided, request_approval
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tenant
from app.core.uploads.models import Upload
from app.modules.finance import ledger
from app.modules.finance.coa import TEMPLATES
from app.modules.finance.gl_models import AccountingPeriod, GlAccount, JournalEntry, LedgerSetup
from app.modules.finance.gl_schemas import AccountIn, JournalIn, SetupIn

APPROVAL_DOC = "journal"


async def _audit(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    target: uuid.UUID,
    summary: dict[str, object],
) -> None:
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=f"finance.{action}",
        target_type=action.split(".")[0],
        target_id=target,
        summary=summary,
    )


async def setup(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: SetupIn
) -> LedgerSetup:
    """FR-FIN-009: seed the chart once, record the start date and post opening balances."""
    if await db.scalar(select(LedgerSetup.id)) is not None:
        raise ConflictError("ledger_already_set_up")
    language = await db.scalar(select(Tenant.language).where(Tenant.id == tenant_id))
    for row in TEMPLATES[data.template]:
        db.add(
            GlAccount(
                tenant_id=tenant_id,
                code=row.code,
                name=row.id_name if language == "id" else row.en_name,
                type=row.type,
                system_key=row.key,
            )
        )
    books = LedgerSetup(
        tenant_id=tenant_id, start_date=data.start_date, template=data.template, created_by=user_id
    )
    db.add(books)
    await db.flush()
    codes = {a.code: a.id for a in await db.scalars(select(GlAccount))}
    if unknown := {o.account_code for o in data.opening} - codes.keys():
        raise NotFoundError("account_not_found", details={"codes": sorted(unknown)})
    lines = [
        ledger.Line(codes[o.account_code], o.debit, o.credit)
        for o in data.opening
        if o.debit or o.credit
    ]
    if lines:
        books.opening_entry_id = (await _opening(db, tenant_id, user_id, data.start_date, lines)).id
    await _audit(
        db, tenant_id, user_id, "ledger.setup", books.id, {"start": data.start_date.isoformat()}
    )
    return books


async def _opening(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, on: date, lines: list[ledger.Line]
) -> JournalEntry:
    gap = sum(ln.debit for ln in lines) - sum(ln.credit for ln in lines)
    if gap:
        equity = await account_by_key(db, "opening_equity")
        lines.append(ledger.Line(equity.id, debit=max(-gap, 0), credit=max(gap, 0)))
    head = ledger.Head(on, "opening", memo="Opening balances")
    return await ledger.write(db, tenant_id=tenant_id, user_id=user_id, head=head, lines=lines)


async def account_by_key(db: AsyncSession, key: str) -> GlAccount:
    row = await db.scalar(select(GlAccount).where(GlAccount.system_key == key))
    if row is None:
        raise NotFoundError("account_not_found", details={"key": key})
    return row


async def save_account(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AccountIn,
    account: GlAccount | None = None,
) -> GlAccount:
    row = account or GlAccount(tenant_id=tenant_id)
    if account is not None and account.system_key and data.type != account.type:
        raise ConflictError("system_account_type_fixed")  # automatic journals rely on it
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("account_code_exists") from None
    await _audit(db, tenant_id, user_id, "account.save", row.id, {"code": row.code})
    return row


async def submit_journal(db: AsyncSession, p: Principal, data: JournalIn) -> JournalEntry:
    """FR-FIN-004: a manual journal is posted at once, or waits for the approver set by the
    approval rules for "journal" (never the person who entered it)."""
    if data.attachment_id:
        upload = await db.get(Upload, data.attachment_id)
        if upload is None:
            raise NotFoundError("upload_not_found")
    head = ledger.Head(
        data.entry_date,
        "manual",
        memo=data.memo,
        outlet_id=data.outlet_id,
        attachment_id=data.attachment_id,
    )
    lines = [ledger.Line(**ln.model_dump()) for ln in data.lines]
    entry = await ledger.write(
        db, tenant_id=p.tenant_id, user_id=p.user_id, head=head, lines=lines, status="submitted"
    )
    roles = await request_approval(
        db,
        APPROVAL_DOC,
        entry,  # type: ignore[arg-type]  # a tenant-wide entry has no outlet
        entry.total,
        number=entry.number,
        link="/finance?tab=journals",
    )
    if not roles:
        entry.status = "posted"
    await db.flush()
    await _audit(
        db,
        p.tenant_id,
        p.user_id,
        "journal.create",
        entry.id,
        {"number": entry.number, "total": entry.total, "status": entry.status},
    )
    return entry


async def get_entry(db: AsyncSession, entry_id: uuid.UUID, *, lock: bool = False) -> JournalEntry:
    row = await db.get(JournalEntry, entry_id, with_for_update=lock)
    if row is None:
        raise NotFoundError("journal_not_found")
    return row


async def decide(db: AsyncSession, entry: JournalEntry, p: Principal, *, approve: bool) -> None:
    if entry.status != "submitted":
        raise ConflictError("wrong_status", details={"status": entry.status})
    roles = await approvers_needed(db, APPROVAL_DOC, entry, entry.total)  # type: ignore[arg-type]
    await ensure_may_decide(db, entry, roles, user_id=p.user_id, role_id=p.role_id)  # type: ignore[arg-type]
    if approve:
        await ledger.ensure_open(db, p.tenant_id, entry.entry_date)  # closed meanwhile?
    mark_decided(entry, "posted" if approve else "rejected", p.user_id)  # type: ignore[arg-type]
    await db.flush()
    verb = "approve" if approve else "reject"
    await _audit(db, p.tenant_id, p.user_id, f"journal.{verb}", entry.id, {"number": entry.number})


async def periods(db: AsyncSession) -> list[AccountingPeriod]:
    stmt = select(AccountingPeriod).order_by(
        AccountingPeriod.year.desc(), AccountingPeriod.month.desc()
    )
    return list(await db.scalars(stmt.limit(60)))


async def set_period(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    month: int,
    close: bool,
) -> AccountingPeriod:
    """FR-FIN-005: closing locks the month; reopening (to correct) is possible and audited."""
    row = await db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.year == year, AccountingPeriod.month == month)
        .with_for_update()
    )
    if row is None:
        row = AccountingPeriod(tenant_id=tenant_id, year=year, month=month)
        db.add(row)
    if close:
        waiting = select(JournalEntry.id).where(
            JournalEntry.status == "submitted",
            JournalEntry.entry_date >= date(year, month, 1),
            JournalEntry.entry_date < _next_month(year, month),
        )
        if await db.scalar(waiting.limit(1)) is not None:
            raise ConflictError("period_has_pending_journals")
    row.status = "closed" if close else "open"
    row.closed_by, row.closed_at = (user_id, datetime.now(UTC)) if close else (None, None)
    await db.flush()
    await _audit(
        db,
        tenant_id,
        user_id,
        "period.close" if close else "period.reopen",
        row.id,
        {"year": year, "month": month},
    )
    return row


def _next_month(year: int, month: int) -> date:
    return date(year + month // 12, month % 12 + 1, 1)


async def give_role(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, account: GlAccount, key: str
) -> GlAccount:
    """FR-FIN-003 posting rules: automatic journals use the account holding a role ("cash",
    "sales", ...). Giving the role to another account of the same type changes the rule."""
    holder = await account_by_key(db, key)
    if holder.id == account.id:
        return account
    if holder.type != account.type or not account.is_active:
        raise ConflictError("role_needs_same_type", details={"type": holder.type})
    holder.system_key = None
    await db.flush()
    account.system_key = key
    await db.flush()
    await _audit(
        db, tenant_id, user_id, "account.role", account.id, {"role": key, "from": holder.code}
    )
    return account
