"""Sales events for other modules (app/core/events.py).

ORDER_PAID: a POS order was paid. Data: order_id, outlet_id.
ORDER_CLOSED: a POS order ended without payment (cancelled or voided). Data: order_id,
outlet_id, status.
"""

ORDER_PAID = "sales.order.paid"
ORDER_CLOSED = "sales.order.closed"
