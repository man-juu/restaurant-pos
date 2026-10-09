"""In-transaction domain events (ADR-012, docs/04 module rules 2 and section 6).

A module publishes a named event with a small payload; modules that depend on it register
handlers in their `events.py`. Handlers run in the publisher's transaction, so the change
and its consequences commit or roll back together (paying an order and freeing its table).
A handler belonging to a module the tenant switched off is skipped.

Keep handlers small: anything slow belongs in a background job, not here."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import TenantModule

Handler = Callable[[AsyncSession, "Event"], Awaitable[None]]


@dataclass(frozen=True)
class Event:
    name: str
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    data: dict[str, Any]


_HANDLERS: dict[str, list[tuple[str, Handler]]] = {}


def subscribe(event: str, module: str, handler: Handler) -> None:
    """Register `handler` for `event` on behalf of `module` (once per handler)."""
    entries = _HANDLERS.setdefault(event, [])
    if (module, handler) not in entries:
        entries.append((module, handler))


async def publish(db: AsyncSession, event: Event) -> None:
    entries = _HANDLERS.get(event.name, [])
    if not entries:
        return
    enabled = set(
        await db.scalars(
            select(TenantModule.module).where(
                TenantModule.tenant_id == event.tenant_id, TenantModule.enabled
            )
        )
    )
    for module, handler in entries:
        if module in enabled:
            await handler(db, event)
