"""Tenant-scoped database sessions (CLAUDE.md rule 1, docs/04 section 7).

Every query against tenant tables must run inside `tenant_session`. It opens a transaction and
calls set_config(..., true): the `true` makes the setting transaction-local, so when the pooled
connection is reused by the next request the tenant is gone. A session-level SET would leak one
tenant's context into another tenant's request. If no tenant is set, the RLS policies match
no rows (fail closed).
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import tenant_id_var, user_id_var

_SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true), "
    "set_config('app.user_id', :user_id, true)"
)


@asynccontextmanager
async def tenant_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield a session in one transaction bound to `tenant_id`. Commits on success, rolls
    back on error. `tenant_id` must come from the server-side session, never from the client."""
    tenant_token = tenant_id_var.set(str(tenant_id))
    user_token = user_id_var.set(str(user_id) if user_id else None)
    try:
        async with sessionmaker() as session, session.begin():
            await session.execute(
                _SET_CONTEXT,
                {"tenant_id": str(tenant_id), "user_id": str(user_id) if user_id else ""},
            )
            yield session
    finally:
        tenant_id_var.reset(tenant_token)
        user_id_var.reset(user_token)
