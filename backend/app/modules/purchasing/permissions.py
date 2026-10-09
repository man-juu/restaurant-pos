VENDOR_VIEW = "purchasing.vendor.view"
VENDOR_MANAGE = "purchasing.vendor.manage"
RECEIPT_CREATE = "purchasing.receipt.create"
RECEIPT_REVERSE = "purchasing.receipt.reverse"
ORDER_CREATE = "purchasing.order.create"
ORDER_APPROVE = "purchasing.order.approve"
REPORT_VIEW = "purchasing.report.view"

ALL = (
    VENDOR_VIEW,
    VENDOR_MANAGE,
    RECEIPT_CREATE,
    RECEIPT_REVERSE,
    ORDER_CREATE,
    ORDER_APPROVE,
    REPORT_VIEW,
)

# docs/03 matrix: "Create purchase request or order" owner/co-owner Y, manager O, warehouse O,
# purchaser Y; "Approve purchase order" manager A. Receiving follows the create row.
_BUY = (VENDOR_VIEW, RECEIPT_CREATE, ORDER_CREATE)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (*_BUY, VENDOR_MANAGE, RECEIPT_REVERSE, ORDER_APPROVE, REPORT_VIEW),
    "warehouse": (*_BUY, REPORT_VIEW),
    "purchaser": (*_BUY, VENDOR_MANAGE, REPORT_VIEW),
    "accountant": (VENDOR_VIEW, REPORT_VIEW),
    "viewer": (VENDOR_VIEW, REPORT_VIEW),
}
