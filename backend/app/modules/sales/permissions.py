DAY_VIEW = "sales.day.view"
DAY_ENTER = "sales.day.enter"  # record manual daily sales
DAY_LOCK = "sales.day.lock"  # lock, and reopen a locked day
REPORT_VIEW = "sales.report.view"

ALL = (DAY_VIEW, DAY_ENTER, DAY_LOCK, REPORT_VIEW)

# docs/03 matrix: "Record manual daily sales": owner/co-owner Y, manager O, cashier O.
# "Lock a sales day": owner/co-owner Y, manager O. "Reports (own scope)": manager O,
# accountant Y, viewer R (warehouse and purchaser read stock and purchase reports).
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (DAY_VIEW, DAY_ENTER, DAY_LOCK, REPORT_VIEW),
    "cashier": (DAY_VIEW, DAY_ENTER),
    "accountant": (DAY_VIEW, REPORT_VIEW),
    "viewer": (DAY_VIEW, REPORT_VIEW),
}
