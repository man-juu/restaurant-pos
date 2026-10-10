"""Loyalty listens to sales (app/core/events.py): voucher tenders are checked and used up in
the payment's transaction, and a refunded receipt takes back its points and vouchers. Where
the module is off these never run and "voucher" stays a plain payment method."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, subscribe
from app.modules.loyalty import service
from app.modules.sales.interface import DOCUMENT_POSTED, DOCUMENT_REVERSED


async def _posted(db: AsyncSession, event: Event) -> None:
    await service.spend_vouchers(db, event.tenant_id, event.data["document_id"])


async def _reversed(db: AsyncSession, event: Event) -> None:
    await service.undo_for_document(db, event.data["document_id"], event.user_id)


def register() -> None:
    subscribe(DOCUMENT_POSTED, "loyalty", _posted)
    subscribe(DOCUMENT_REVERSED, "loyalty", _reversed)
