"""Kitchen listens to sales (app/core/events.py): sent lines become tickets, voided lines
are struck through on the display."""

from app.core.events import subscribe
from app.modules.kitchen import service
from app.modules.sales.interface import LINES_SENT, LINES_VOIDED


def register() -> None:
    subscribe(LINES_SENT, "kitchen", service.on_lines_sent)
    subscribe(LINES_VOIDED, "kitchen", service.on_lines_voided)
