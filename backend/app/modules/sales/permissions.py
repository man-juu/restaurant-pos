DAY_VIEW = "sales.day.view"
DAY_ENTER = "sales.day.enter"  # record manual daily sales
DAY_LOCK = "sales.day.lock"  # lock, and reopen a locked day
REPORT_VIEW = "sales.report.view"
ORDER_CREATE = "sales.order.create"  # take and edit POS orders
ORDER_PAY = "sales.order.pay"  # take payment for an order
SHIFT_OPEN = "sales.shift.open"  # open and close one's own cash shift
SHIFT_VIEW = "sales.shift.view"  # see every shift's figures and close others' shifts
DISCOUNT_APPLY = "sales.discount.apply"  # up to the role's limit (basis points)
ORDER_VOID = "sales.order.void"  # void sent lines or an unpaid order, with a reason
ORDER_REFUND = "sales.order.refund"  # refund a paid order (approval by rule)
STAFF_VIEW = "sales.staff.view"  # FR-RPT-012: sales by staff member

ALL = (
    DAY_VIEW,
    DAY_ENTER,
    DAY_LOCK,
    REPORT_VIEW,
    ORDER_CREATE,
    ORDER_PAY,
    SHIFT_OPEN,
    SHIFT_VIEW,
    DISCOUNT_APPLY,
    ORDER_VOID,
    ORDER_REFUND,
    STAFF_VIEW,
)

# docs/03 matrix: "Record manual daily sales": owner/co-owner Y, manager O, cashier O.
# "Lock a sales day": owner/co-owner Y, manager O. "Reports (own scope)": manager O,
# accountant Y, viewer R (warehouse and purchaser read stock and purchase reports).
# "Take and edit POS orders": manager, cashier, waiter O. "Open and close cash shift":
# manager, cashier O, accountant R. Waiters take orders but do not take money.
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (
        DAY_VIEW,
        DAY_ENTER,
        DAY_LOCK,
        REPORT_VIEW,
        ORDER_CREATE,
        ORDER_PAY,
        SHIFT_OPEN,
        SHIFT_VIEW,
        DISCOUNT_APPLY,
        ORDER_VOID,
        ORDER_REFUND,
        STAFF_VIEW,
    ),
    "cashier": (
        DAY_VIEW,
        DAY_ENTER,
        ORDER_CREATE,
        ORDER_PAY,
        SHIFT_OPEN,
        DISCOUNT_APPLY,
        ORDER_VOID,
        ORDER_REFUND,
    ),
    "waiter": (ORDER_CREATE,),
    "accountant": (DAY_VIEW, REPORT_VIEW, SHIFT_VIEW, STAFF_VIEW),
    "viewer": (DAY_VIEW, REPORT_VIEW),
}

# docs/03 rule 7 and section 7 "Discount: cashier up to a role limit; manager above".
# Defaults, changed per role in Settings > Limits. Owners have no limit.
LIMIT_UNITS = {DISCOUNT_APPLY: "bp"}
ROLE_LIMITS: dict[str, dict[str, int]] = {
    "cashier": {DISCOUNT_APPLY: 1000},  # 10 %
    "manager": {DISCOUNT_APPLY: 5000},  # 50 %
}
