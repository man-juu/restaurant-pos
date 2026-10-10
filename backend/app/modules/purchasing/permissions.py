VENDOR_VIEW = "purchasing.vendor.view"
VENDOR_MANAGE = "purchasing.vendor.manage"
RECEIPT_CREATE = "purchasing.receipt.create"
RECEIPT_REVERSE = "purchasing.receipt.reverse"
ORDER_CREATE = "purchasing.order.create"
ORDER_APPROVE = "purchasing.order.approve"
REPORT_VIEW = "purchasing.report.view"
RETURN_CREATE = "purchasing.return.create"  # FR-PUR-008
BILL_VIEW = "purchasing.bill.view"  # FR-PUR-009
BILL_MANAGE = "purchasing.bill.manage"  # enter, void, credit notes and credits
BILL_PAY = "purchasing.bill.pay"

ALL = (
    VENDOR_VIEW,
    VENDOR_MANAGE,
    RECEIPT_CREATE,
    RECEIPT_REVERSE,
    ORDER_CREATE,
    ORDER_APPROVE,
    REPORT_VIEW,
    RETURN_CREATE,
    BILL_VIEW,
    BILL_MANAGE,
    BILL_PAY,
)

# docs/03 matrix: "Create purchase request or order" owner/co-owner Y, manager O, warehouse O,
# purchaser Y; "Approve purchase order" manager A. Receiving follows the create row.
# Returns follow receiving; bills and payments are the accountant's (docs/03 finance rows).
_BUY = (VENDOR_VIEW, RECEIPT_CREATE, ORDER_CREATE, RETURN_CREATE)
_BILLS = (BILL_VIEW, BILL_MANAGE)  # paying is finance: accountant (owners have everything)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (
        *_BUY,
        BILL_VIEW,
        BILL_MANAGE,
        VENDOR_MANAGE,
        RECEIPT_REVERSE,
        ORDER_APPROVE,
        REPORT_VIEW,
    ),
    "warehouse": (*_BUY, REPORT_VIEW),
    "purchaser": (*_BUY, *_BILLS, VENDOR_MANAGE, REPORT_VIEW),
    "accountant": (VENDOR_VIEW, REPORT_VIEW, *_BILLS, BILL_PAY),
    "viewer": (VENDOR_VIEW, REPORT_VIEW, BILL_VIEW),
}
