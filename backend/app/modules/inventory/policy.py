"""FR-INV-006: may this posting take more than is on hand? Callers (sales, production,
transfers, waste) ask here before `service.consume`, so the tenant setting decides."""

import uuid
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import service as settings
from app.core.settings.schemas import StockSettings

ShortageKind = Literal["sale", "production", "transfer", "other"]


async def negative_allowed(
    db: AsyncSession, tenant_id: uuid.UUID, kind: ShortageKind, *, confirmed: bool
) -> bool:
    """ "allow": yes; "warn": only after the user confirmed; "block": never."""
    stock = cast(StockSettings, await settings.get_setting(db, tenant_id, "stock"))
    policy = getattr(stock.negative_stock, kind)
    return policy == "allow" or (policy == "warn" and confirmed)
