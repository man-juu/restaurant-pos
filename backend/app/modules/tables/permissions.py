TABLE_VIEW = "tables.table.view"  # see floors, tables and who sits where
TABLE_SETUP = "tables.table.setup"  # add and change floors and tables
SESSION_MANAGE = "tables.session.manage"  # seat, move, merge, split, mark clean

ALL = (TABLE_VIEW, TABLE_SETUP, SESSION_MANAGE)

# docs/03 matrix "Manage tables and reservations": manager, cashier, waiter O.
_FLOOR = (TABLE_VIEW, SESSION_MANAGE)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (TABLE_VIEW, TABLE_SETUP, SESSION_MANAGE),
    "cashier": _FLOOR,
    "waiter": _FLOOR,
    "kitchen": (TABLE_VIEW,),
    "viewer": (TABLE_VIEW,),
}
