ORDER_VIEW = "production.order.view"
ORDER_MANAGE = "production.order.manage"  # plan, complete, cancel
ORDER_REVERSE = "production.order.reverse"

ALL = (ORDER_VIEW, ORDER_MANAGE, ORDER_REVERSE)

# docs/03 matrix "Production orders": owner/co-owner Y, manager O, kitchen O, warehouse O.
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (ORDER_VIEW, ORDER_MANAGE, ORDER_REVERSE),
    "kitchen": (ORDER_VIEW, ORDER_MANAGE),
    "warehouse": (ORDER_VIEW, ORDER_MANAGE),
    "viewer": (ORDER_VIEW,),
}
