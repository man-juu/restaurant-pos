"""Outgoing demand on an outlet's stock that other modules know about (FR-PRD-008).

The central kitchen's prep list adds what branches have asked for. Requests live in the
transfers module, which production does not depend on; so, like ledger invariants, a module
registers a provider here and the prep list asks every provider of a switched-on module.
A provider returns item -> quantity (base unit) still to send from the outlet by `until`."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import TenantModule

Provider = Callable[[AsyncSession, uuid.UUID, date], Awaitable[dict[uuid.UUID, Decimal]]]
_providers: dict[str, Provider] = {}


def register_demand(module: str, provider: Provider) -> None:
    _providers[module] = provider


async def outgoing_demand(
    db: AsyncSession, tenant_id: uuid.UUID, outlet_id: uuid.UUID, until: date
) -> dict[uuid.UUID, Decimal]:
    if not _providers:
        return {}
    enabled = set(
        await db.scalars(
            select(TenantModule.module).where(
                TenantModule.tenant_id == tenant_id, TenantModule.enabled
            )
        )
    )
    total: dict[uuid.UUID, Decimal] = {}
    for module, provider in sorted(_providers.items()):
        if module not in enabled:
            continue
        for item_id, qty in (await provider(db, outlet_id, until)).items():
            total[item_id] = total.get(item_id, Decimal(0)) + qty
    return total
