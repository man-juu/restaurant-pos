"""Sales events for other modules (app/core/events.py).

ORDER_PAID: a POS order was paid. Data: order_id, outlet_id.
ORDER_CLOSED: a POS order ended without payment (cancelled or voided). Data: order_id,
outlet_id, status.
DOCUMENT_POSTED: a sales document (a paid POS order or a daily sales entry) is in the books.
DOCUMENT_REVERSED: it was refunded or replaced. Data: document_id. Finance journals both
(FR-FIN-003).
"""

ORDER_PAID = "sales.order.paid"
ORDER_CLOSED = "sales.order.closed"
LINES_SENT = "sales.lines.sent"  # Data: order_id, outlet_id, line_ids (to the kitchen)
LINES_VOIDED = "sales.lines.voided"  # Data: order_id, outlet_id, line_ids
DOCUMENT_POSTED = "sales.document.posted"
DOCUMENT_REVERSED = "sales.document.reversed"
