ITEM_VIEW = "catalog.item.view"
ITEM_CREATE = "catalog.item.create"
ITEM_UPDATE = "catalog.item.update"
COST_VIEW = "catalog.cost.view"
AVAILABILITY = "catalog.item.availability"  # mark sold out / back on sale (FR-CAT-003)

ALL = (ITEM_VIEW, ITEM_CREATE, ITEM_UPDATE, COST_VIEW, AVAILABILITY)

# docs/03 section 4 matrix ("Edit items, menu, recipes, prices"; "See item cost and margin").
_EDIT = (ITEM_VIEW, ITEM_CREATE, ITEM_UPDATE, COST_VIEW, AVAILABILITY)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": _EDIT,
    "cashier": (ITEM_VIEW, AVAILABILITY),
    "waiter": (ITEM_VIEW,),
    "kitchen": (ITEM_VIEW, AVAILABILITY),
    "warehouse": (ITEM_VIEW, COST_VIEW),
    "purchaser": (ITEM_VIEW, COST_VIEW),
    "accountant": (ITEM_VIEW, COST_VIEW),
    "viewer": (ITEM_VIEW, COST_VIEW),
}
