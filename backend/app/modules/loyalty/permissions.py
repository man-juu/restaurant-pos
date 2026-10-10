POINTS_VIEW = "loyalty.points.view"  # a guest's points, history and vouchers
POINTS_EARN = "loyalty.points.earn"  # give points for a paid receipt
POINTS_REDEEM = "loyalty.points.redeem"  # turn points into a voucher
VOUCHER_MANAGE = "loyalty.voucher.manage"  # issue and void vouchers by hand

ALL = (POINTS_VIEW, POINTS_EARN, POINTS_REDEEM, VOUCHER_MANAGE)

_TILL = (POINTS_VIEW, POINTS_EARN, POINTS_REDEEM)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": ALL,
    "cashier": _TILL,
    "waiter": (POINTS_VIEW, POINTS_EARN),
    "viewer": (POINTS_VIEW,),
}
