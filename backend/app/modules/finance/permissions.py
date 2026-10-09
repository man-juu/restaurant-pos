EXPENSE_VIEW = "finance.expense.view"
EXPENSE_CREATE = "finance.expense.create"  # record and reverse expenses, move money
ACCOUNT_MANAGE = "finance.account.manage"  # accounts and expense categories
REPORT_VIEW = "finance.report.view"  # profit and loss

ALL = (EXPENSE_VIEW, EXPENSE_CREATE, ACCOUNT_MANAGE, REPORT_VIEW)

# docs/03 matrix "Journals, expenses, period close": owner, co-owner, accountant Y;
# viewer R. Managers can be given expenses per tenant (roles are editable).
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "accountant": ALL,
    "viewer": (EXPENSE_VIEW, REPORT_VIEW),
}
