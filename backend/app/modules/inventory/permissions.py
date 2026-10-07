STOCK_VIEW = "inventory.stock.view"
OPENING_POST = "inventory.opening.post"

ALL = (STOCK_VIEW, OPENING_POST)

# docs/03 section 4: stock screens follow "Reports (own scope)" plus the roles that count and
# log waste (kitchen); entering opening stock is setup work for managers and storekeepers.
# Counts, waste and adjustments add their own permissions in slice 1i.
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (STOCK_VIEW, OPENING_POST),
    "warehouse": (STOCK_VIEW, OPENING_POST),
    "kitchen": (STOCK_VIEW,),
    "purchaser": (STOCK_VIEW,),
    "accountant": (STOCK_VIEW,),
    "viewer": (STOCK_VIEW,),
}
