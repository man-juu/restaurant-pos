"""Finance-lite (FR-FIN-001): accounts, categories, expenses, transfers and profit and loss.
Expenses are never deleted: a mistake is reversed (status "reversed", audited)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.reports import Period
from app.core.settings import service as settings
from app.modules.finance.models import Expense, ExpenseCategory, MoneyAccount, MoneyTransfer
from app.modules.finance.schemas import (
    ExpenseCategoryIn,
    ExpenseIn,
    MoneyAccountIn,
    MoneyAccountOut,
    ProfitLossOut,
    TransferIn,
)
from app.modules.inventory.interface import visible_outlet
from app.modules.sales.interface import period_totals


async def _record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    target: str,
    target_id: uuid.UUID,
    summary: dict[str, object],
    outlet_id: uuid.UUID | None = None,
) -> None:
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        outlet_id=outlet_id,
        action=f"finance.{action}",
        target_type=target,
        target_id=target_id,
        summary=summary,
    )


async def _save(db: AsyncSession, row: object, taken: str) -> None:
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError(taken) from None


async def save_account(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: MoneyAccountIn,
    account_id: uuid.UUID | None = None,
) -> MoneyAccount:
    if data.outlet_id is not None:
        await visible_outlet(db, data.outlet_id)
    if account_id is None:
        row = MoneyAccount(tenant_id=tenant_id, **data.model_dump())
    else:
        found = await db.get(MoneyAccount, account_id, with_for_update=True)
        if found is None:
            raise NotFoundError("account_not_found")
        row = found
        for key, value in data.model_dump().items():
            setattr(row, key, value)
    await _save(db, row, "account_name_taken")
    await _record(
        db, tenant_id, user_id, "account.save", "money_account", row.id, {"name": row.name}
    )
    return row


async def balances(db: AsyncSession) -> list[MoneyAccountOut]:
    accounts = list(await db.scalars(select(MoneyAccount).order_by(MoneyAccount.name)))
    spent = dict(
        (
            await db.execute(
                select(Expense.account_id, func.sum(Expense.amount))
                .where(Expense.status == "posted")
                .group_by(Expense.account_id)
            )
        ).all()
    )
    out_ = dict(
        (
            await db.execute(
                select(MoneyTransfer.from_account_id, func.sum(MoneyTransfer.amount)).group_by(
                    MoneyTransfer.from_account_id
                )
            )
        ).all()
    )
    in_ = dict(
        (
            await db.execute(
                select(MoneyTransfer.to_account_id, func.sum(MoneyTransfer.amount)).group_by(
                    MoneyTransfer.to_account_id
                )
            )
        ).all()
    )
    return [
        MoneyAccountOut(
            id=a.id,
            name=a.name,
            kind=a.kind,  # type: ignore[arg-type]
            outlet_id=a.outlet_id,
            opening_balance=a.opening_balance,
            is_active=a.is_active,
            balance=a.opening_balance
            + int(in_.get(a.id, 0))
            - int(out_.get(a.id, 0))
            - int(spent.get(a.id, 0)),
        )
        for a in accounts
    ]


async def save_category(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ExpenseCategoryIn,
    category_id: uuid.UUID | None = None,
) -> ExpenseCategory:
    if category_id is None:
        row = ExpenseCategory(tenant_id=tenant_id, **data.model_dump())
    else:
        found = await db.get(ExpenseCategory, category_id, with_for_update=True)
        if found is None:
            raise NotFoundError("category_not_found")
        row = found
        row.name, row.is_active = data.name, data.is_active
    await _save(db, row, "category_name_taken")
    await _record(
        db, tenant_id, user_id, "category.save", "expense_category", row.id, {"name": row.name}
    )
    return row


async def _active(
    db: AsyncSession,
    model: type[MoneyAccount] | type[ExpenseCategory],
    row_id: uuid.UUID,
    code: str,
) -> None:
    row: MoneyAccount | ExpenseCategory | None = await db.get(model, row_id)
    if row is None or not row.is_active:
        raise NotFoundError(code)


async def add_expense(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, data: ExpenseIn
) -> Expense:
    await visible_outlet(db, data.outlet_id)
    await _active(db, MoneyAccount, data.account_id, "account_not_found")
    await _active(db, ExpenseCategory, data.category_id, "category_not_found")
    number = await settings.allocate_number(
        db, tenant_id=tenant_id, doc_type="expense", on=data.spent_on
    )
    row = Expense(tenant_id=tenant_id, number=number, created_by=user_id, **data.model_dump())
    await _save(db, row, "expense_conflict")
    await _record(
        db,
        tenant_id,
        user_id,
        "expense.create",
        "expense",
        row.id,
        {"number": number, "amount": data.amount},
        data.outlet_id,
    )
    return row


async def reverse_expense(db: AsyncSession, row: Expense, user_id: uuid.UUID) -> None:
    if row.status != "posted":
        raise ConflictError("wrong_status", details={"status": row.status})
    row.status, row.reversed_by, row.reversed_at = "reversed", user_id, datetime.now(UTC)
    await db.flush()
    await _record(
        db,
        row.tenant_id,
        user_id,
        "expense.reverse",
        "expense",
        row.id,
        {"number": row.number, "amount": row.amount},
        row.outlet_id,
    )


async def transfer(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, data: TransferIn
) -> MoneyTransfer:
    if data.from_account_id == data.to_account_id:
        raise ConflictError("same_account")
    for account in (data.from_account_id, data.to_account_id):
        await _active(db, MoneyAccount, account, "account_not_found")
    row = MoneyTransfer(tenant_id=tenant_id, created_by=user_id, **data.model_dump())
    await _save(db, row, "transfer_conflict")
    await _record(
        db, tenant_id, user_id, "transfer", "money_transfer", row.id, {"amount": data.amount}
    )
    return row


async def profit_loss(
    db: AsyncSession, period: Period, outlets: list[uuid.UUID] | None
) -> ProfitLossOut:
    sales = await period_totals(db, period, outlets)
    stmt = (
        select(ExpenseCategory.name, func.sum(Expense.amount))
        .join(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .where(
            Expense.status == "posted",
            Expense.spent_on >= period.date_from,
            Expense.spent_on <= period.date_to,
        )
        .group_by(ExpenseCategory.name)
        .order_by(ExpenseCategory.name)
    )
    if outlets is not None:
        stmt = stmt.where(Expense.outlet_id.in_(outlets))
    expenses = {name: int(total) for name, total in (await db.execute(stmt)).all()}
    revenue = sales.net_sales + sales.service_charge
    gross = revenue - sales.cost
    spent = sum(expenses.values())
    return ProfitLossOut(
        net_sales=sales.net_sales,
        service_charge=sales.service_charge,
        revenue=revenue,
        cost_of_sales=sales.cost,
        gross_profit=gross,
        expenses=expenses,
        expenses_total=spent,
        net_profit=gross - spent,
        tax_collected=sales.tax,
    )
