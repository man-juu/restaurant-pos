DAY_VIEW = "sales.day.view"
DAY_ENTER = "sales.day.enter"  # record manual daily sales
DAY_LOCK = "sales.day.lock"  # lock, and reopen a locked day

ALL = (DAY_VIEW, DAY_ENTER, DAY_LOCK)

# docs/03 matrix: "Record manual daily sales": owner/co-owner Y, manager O, cashier O.
# "Lock a sales day": owner/co-owner Y, manager O. Reports readers may view.
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (DAY_VIEW, DAY_ENTER, DAY_LOCK),
    "cashier": (DAY_VIEW, DAY_ENTER),
    "accountant": (DAY_VIEW,),
    "viewer": (DAY_VIEW,),
}
