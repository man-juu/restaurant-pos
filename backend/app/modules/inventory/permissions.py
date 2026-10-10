STOCK_VIEW = "inventory.stock.view"
OPENING_POST = "inventory.opening.post"
WASTE_CREATE = "inventory.waste.create"
COUNT_CREATE = "inventory.count.create"
COUNT_APPROVE = "inventory.count.approve"
ADJUSTMENT_CREATE = "inventory.adjustment.create"
ADJUSTMENT_APPROVE = "inventory.adjustment.approve"  # also reverses a waste log
LEVEL_MANAGE = "inventory.level.manage"  # par, min, reorder point, max per outlet
REPORT_VIEW = "inventory.report.view"  # docs/03 "Reports (own scope)"

ALL = (
    STOCK_VIEW,
    OPENING_POST,
    WASTE_CREATE,
    COUNT_CREATE,
    COUNT_APPROVE,
    ADJUSTMENT_CREATE,
    ADJUSTMENT_APPROVE,
    LEVEL_MANAGE,
    REPORT_VIEW,
)

# docs/03 section 4: stock screens follow "Reports (own scope)" plus the roles that count and
# log waste (kitchen); opening stock is setup work for managers and storekeepers. "Waste
# log" and "Stock count (enter)": manager, kitchen, warehouse. "Stock count and adjustment
# (approve)": manager (owner and co-owner have every permission).
_FLOOR = (STOCK_VIEW, WASTE_CREATE, COUNT_CREATE)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (
        *_FLOOR,
        OPENING_POST,
        ADJUSTMENT_CREATE,
        COUNT_APPROVE,
        ADJUSTMENT_APPROVE,
        LEVEL_MANAGE,
        REPORT_VIEW,
    ),
    "warehouse": (*_FLOOR, OPENING_POST, ADJUSTMENT_CREATE, LEVEL_MANAGE, REPORT_VIEW),
    "kitchen": _FLOOR,
    "purchaser": (STOCK_VIEW, REPORT_VIEW),
    "accountant": (STOCK_VIEW, REPORT_VIEW),
    "viewer": (STOCK_VIEW, REPORT_VIEW),
}
