"""Periodic tasks (docs/04 section 10): work a module wants done for each tenant on a
schedule, such as creating standing transfer requests (FR-TRF-005). The worker's alerts job
(every 10 minutes) runs them in the tenant's own RLS context, one transaction per tenant.
Tasks must be idempotent: they run many times a day. Only switched-on modules run."""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import TenantModule

Task = Callable[[AsyncSession, uuid.UUID], Awaitable[int]]
_tasks: dict[str, Task] = {}


def register_task(module: str, task: Task) -> None:
    _tasks[module] = task


async def run_tasks(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Runs every task of the tenant's switched-on modules; returns what they created."""
    if not _tasks:
        return 0
    enabled = set(
        await db.scalars(
            select(TenantModule.module).where(
                TenantModule.tenant_id == tenant_id, TenantModule.enabled
            )
        )
    )
    return sum([await task(db, tenant_id) for m, task in sorted(_tasks.items()) if m in enabled])
