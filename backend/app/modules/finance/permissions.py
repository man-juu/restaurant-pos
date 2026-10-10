EXPENSE_VIEW = "finance.expense.view"
EXPENSE_CREATE = "finance.expense.create"  # record and reverse expenses, move money
ACCOUNT_MANAGE = "finance.account.manage"  # accounts and expense categories
REPORT_VIEW = "finance.report.view"  # profit and loss

LEDGER_VIEW = "finance.ledger.view"  # chart, journals, trial balance and statements
LEDGER_SETUP = "finance.ledger.setup"  # start date, opening balances, chart of accounts
JOURNAL_CREATE = "finance.journal.create"  # manual journals and reversals; decide approvals
PERIOD_CLOSE = "finance.period.close"  # close and reopen months
SETTLEMENT_MANAGE = "finance.settlement.manage"  # record and reverse platform payouts

ALL = (
    EXPENSE_VIEW,
    EXPENSE_CREATE,
    ACCOUNT_MANAGE,
    REPORT_VIEW,
    LEDGER_VIEW,
    LEDGER_SETUP,
    JOURNAL_CREATE,
    PERIOD_CLOSE,
    SETTLEMENT_MANAGE,
)

# docs/03 matrix "Journals, expenses, period close": owner, co-owner, accountant Y;
# viewer R. Managers can be given expenses per tenant (roles are editable).
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "accountant": ALL,
    "viewer": (EXPENSE_VIEW, REPORT_VIEW, LEDGER_VIEW),
}
