"""Automatic journals from operations (FR-FIN-003).

Sales, stock and purchasing announce what they post (in-transaction events); this module
turns each announcement into a balanced journal in the same transaction, so the books never
lag the documents (CLAUDE.md rule 3). Which account each line uses is found by the account's
role (`system_key`): giving that role to another account changes the posting rule. Nothing is
journaled before the books' start date, or when the tenant switches automatic journals off."""

import uuid
from datetime import date
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event
from app.core.settings import service as settings
from app.core.settings.schemas import FinanceSettings
from app.modules.catalog.interface import tenant_today
from app.modules.finance import ledger
from app.modules.finance.gl_models import GlAccount, JournalEntry, LedgerSetup
from app.modules.finance.models import Expense, ExpenseCategory, MoneyAccount, MoneyTransfer
from app.modules.sales.interface import document_money

# movement type -> (debit role, credit role, normal sign of the value). A value of the other
# sign (a reversal) swaps the sides. Same roles on both sides: nothing to journal.
STOCK_RULES: dict[str, tuple[str, str, int]] = {
    "opening_balance": ("inventory", "opening_equity", 1),
    "sale_consumption": ("cogs", "inventory", -1),
    "production_consumption": ("inventory", "inventory", -1),
    "production_output": ("inventory", "inventory", 1),
    "transfer_out": ("inventory_transit", "inventory", -1),
    "transfer_in": ("inventory", "inventory_transit", 1),
    "waste": ("waste", "inventory", -1),
    "vendor_return": ("payable", "inventory", -1),
    "adjustment": ("inventory", "inventory_variance", 1),
    "count_correction": ("inventory", "inventory_variance", 1),
}
# Stock from goods receipts is journaled from the purchasing event (it knows the vendor).
STOCK_SKIP = {"goods_receipt"}
PAYMENT_ROLES = {
    "cash": "cash",
    "bank_transfer": "bank",
    "qris_static": "card_receivable",
    "card_terminal": "card_receivable",
    "ewallet": "card_receivable",
    "platform_settlement": "platform_receivable",
    "house_account": "receivable",
    "voucher": "discounts",
}
CHANNEL_ROLES = {"platform": "platform_receivable", "wholesale": "receivable"}


async def ready(db: AsyncSession, tenant_id: uuid.UUID, day: date) -> bool:
    books: LedgerSetup | None = await db.scalar(select(LedgerSetup))
    if books is None or day < books.start_date:
        return False
    conf = cast(FinanceSettings, await settings.get_setting(db, tenant_id, "finance"))
    return conf.auto_journals


async def _roles(db: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await db.execute(
        select(GlAccount.system_key, GlAccount.id).where(GlAccount.system_key.is_not(None))
    )
    return {str(k): i for k, i in rows.all()}


def _pair(
    roles: dict[str, uuid.UUID], debit: str, credit: str, amount: int, outlet: uuid.UUID | None
) -> list[ledger.Line]:
    if amount < 0:
        debit, credit, amount = credit, debit, -amount
    if amount == 0 or debit == credit:
        return []
    return [
        ledger.Line(roles[debit], debit=amount, outlet_id=outlet),
        ledger.Line(roles[credit], credit=amount, outlet_id=outlet),
    ]


async def _post(
    db: AsyncSession,
    event: Event,
    day: date,
    source: tuple[str, uuid.UUID],
    lines: list[ledger.Line],
    memo: str,
) -> None:
    if not lines:
        return
    head = ledger.Head(day, source[0], source[1], memo, lines[0].outlet_id)
    await ledger.write(db, tenant_id=event.tenant_id, user_id=event.user_id, head=head, lines=lines)


async def on_stock(db: AsyncSession, event: Event) -> None:
    d = event.data
    day = date.fromisoformat(str(d["business_date"]))
    if d["doc_type"] in STOCK_SKIP or not await ready(db, event.tenant_id, day):
        return
    roles = await _roles(db)
    outlet = uuid.UUID(str(d["outlet_id"]))
    lines: list[ledger.Line] = []
    for kind, value in cast(dict[str, int], d["values"]).items():
        if kind in STOCK_RULES:
            debit, credit, sign = STOCK_RULES[kind]
            lines += _pair(roles, debit, credit, value * sign, outlet)
    await _post(
        db,
        event,
        day,
        (f"stock.{d['doc_type']}", uuid.UUID(str(d["doc_id"]))),
        lines,
        str(d["doc_type"]),
    )


async def on_sale(db: AsyncSession, event: Event) -> None:
    m = await document_money(db, uuid.UUID(str(event.data["document_id"])))
    if not await ready(db, event.tenant_id, m.business_date):
        return
    roles = await _roles(db)
    received = dict(m.paid) or {"_channel": m.total}
    debits = [
        ledger.Line(
            roles[PAYMENT_ROLES.get(kind, CHANNEL_ROLES.get(m.channel_kind, "cash"))],
            debit=amount,
            outlet_id=m.outlet_id,
        )
        for kind, amount in received.items()
        if amount > 0
    ]
    credits = [
        ((m.channel_kind == "wholesale" and "wholesale_sales") or "sales", -m.subtotal),
        ("discounts", m.discount),
        ("service_charge", -m.service_charge),
        ("tax_payable", -m.tax),
        ("tips_payable", -m.tip),
        ("rounding", -m.rounding),
    ]
    lines = debits + [
        ledger.Line(roles[role], debit=max(v, 0), credit=max(-v, 0), outlet_id=m.outlet_id)
        for role, v in credits
        if v
    ]
    await _post(db, event, m.business_date, ("sales_document", m.id), lines, m.number)


async def reverse_source(
    db: AsyncSession, event: Event, source_type: str, source_id: uuid.UUID
) -> None:
    """Undo the journal of a document that was refunded, replaced or reversed."""
    stmt = select(JournalEntry).where(
        JournalEntry.source_doc_type == source_type,
        JournalEntry.source_doc_id == source_id,
        JournalEntry.status == "posted",
        JournalEntry.reverses_id.is_(None),
    )
    on = await tenant_today(db, event.tenant_id)
    for entry in list(await db.scalars(stmt)):
        done = select(JournalEntry.id).where(JournalEntry.reverses_id == entry.id)
        if await db.scalar(done) is None:
            await ledger.reverse(
                db, entry, user_id=event.user_id or entry.created_by, on=on, memo=None
            )


async def on_sale_reversed(db: AsyncSession, event: Event) -> None:
    await reverse_source(db, event, "sales_document", uuid.UUID(str(event.data["document_id"])))


async def on_receipt(db: AsyncSession, event: Event) -> None:
    d = event.data
    day = date.fromisoformat(str(d["business_date"]))
    if not await ready(db, event.tenant_id, day):
        return
    roles = await _roles(db)
    credit = "payable" if d["on_account"] else "cash"
    lines = _pair(
        roles, "inventory", credit, int(cast(int, d["total"])), uuid.UUID(str(d["outlet_id"]))
    )
    await _post(
        db, event, day, ("goods_receipt", uuid.UUID(str(d["receipt_id"]))), lines, "goods receipt"
    )


async def on_receipt_reversed(db: AsyncSession, event: Event) -> None:
    await reverse_source(db, event, "goods_receipt", uuid.UUID(str(event.data["receipt_id"])))


async def on_bill_paid(db: AsyncSession, event: Event) -> None:
    d = event.data
    day = date.fromisoformat(str(d["paid_on"]))
    if not await ready(db, event.tenant_id, day):
        return
    roles = await _roles(db)
    cash = PAYMENT_ROLES.get(str(d["method_kind"]), "bank")
    lines = _pair(
        roles, "payable", cash, int(cast(int, d["amount"])), uuid.UUID(str(d["outlet_id"]))
    )
    await _post(
        db, event, day, ("vendor_payment", uuid.UUID(str(d["bill_id"]))), lines, "vendor payment"
    )


async def on_receivable_paid(db: AsyncSession, event: Event) -> None:
    """A wholesale customer paid (FR-FIN-006): Dr cash or bank, Cr receivable."""
    d = event.data
    day = date.fromisoformat(str(d["paid_on"]))
    if not await ready(db, event.tenant_id, day):
        return
    roles = await _roles(db)
    cash = PAYMENT_ROLES.get(str(d["method_kind"]), "bank")
    amount = int(cast(int, d["amount"]))
    lines = _pair(roles, cash, "receivable", amount, uuid.UUID(str(d["outlet_id"])))
    source = ("customer_payment", uuid.UUID(str(d["receivable_id"])))
    await _post(db, event, day, source, lines, "customer payment")


# ─── Finance's own documents (expenses, money moved between accounts) ─────────

MONEY_ROLES = {"cash": "cash", "petty_cash": "cash", "bank": "bank"}


async def journal_expense(db: AsyncSession, row: Expense, user_id: uuid.UUID) -> None:
    """Dr the category's account (else other expenses), Cr the cash or bank it was paid from."""
    if not await ready(db, row.tenant_id, row.spent_on):
        return
    roles = await _roles(db)
    category = await db.get(ExpenseCategory, row.category_id)
    paid_from = await db.get(MoneyAccount, row.account_id)
    expense = (
        category.gl_account_id if category and category.gl_account_id else roles["other_expense"]
    )
    source = roles[MONEY_ROLES.get(paid_from.kind if paid_from else "cash", "cash")]
    lines = [
        ledger.Line(expense, debit=row.amount, outlet_id=row.outlet_id),
        ledger.Line(source, credit=row.amount, outlet_id=row.outlet_id),
    ]
    head = ledger.Head(row.spent_on, "expense", row.id, row.number, row.outlet_id)
    await ledger.write(db, tenant_id=row.tenant_id, user_id=user_id, head=head, lines=lines)


async def journal_transfer(db: AsyncSession, row: MoneyTransfer, user_id: uuid.UUID) -> None:
    """Cash into the bank (or back): only when the two sit on different ledger accounts."""
    if not await ready(db, row.tenant_id, row.moved_on):
        return
    kinds = [await db.get(MoneyAccount, i) for i in (row.from_account_id, row.to_account_id)]
    source, target = (MONEY_ROLES.get(k.kind if k else "cash", "cash") for k in kinds)
    lines = _pair(await _roles(db), target, source, row.amount, None)
    if lines:
        head = ledger.Head(row.moved_on, "money_transfer", row.id, None, None)
        await ledger.write(db, tenant_id=row.tenant_id, user_id=user_id, head=head, lines=lines)


async def reverse_own(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> None:
    event = Event("finance.reverse", tenant_id, user_id, {})
    await reverse_source(db, event, source_type, source_id)
