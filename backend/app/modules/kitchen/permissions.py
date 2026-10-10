TICKET_VIEW = "kitchen.ticket.view"  # see the kitchen display
TICKET_UPDATE = "kitchen.ticket.update"  # start, ready, bump, recall
STATION_MANAGE = "kitchen.station.manage"  # set up stations and their categories

ALL = (TICKET_VIEW, TICKET_UPDATE, STATION_MANAGE)

# docs/03 matrix "Kitchen display actions": manager O, kitchen O. Floor staff may look.
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": (TICKET_VIEW, TICKET_UPDATE, STATION_MANAGE),
    "kitchen": (TICKET_VIEW, TICKET_UPDATE),
    "cashier": (TICKET_VIEW,),
    "waiter": (TICKET_VIEW,),
}
