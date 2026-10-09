"""Alerts job (docs/04 section 10): for every active tenant, run the registered alert
scanners in that tenant's own RLS context, one transaction per tenant, so one tenant's
failure never touches another's data. The platform role only lists tenants."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules
from app.core.models import Subscription, Tenant
from app.core.modules import discover
from app.core.notifications.service import run_scanners
from app.core.tenancy import tenant_session

log = logging.getLogger(__name__)


async def active_tenants(admin_db: AsyncSession) -> list[uuid.UUID]:
    stmt = (
        select(Tenant.id)
        .join(Subscription, Subscription.tenant_id == Tenant.id)
        .where(Subscription.suspended.is_(False))
    )
    return list(await admin_db.scalars(stmt))


async def run_alerts(
    tenant_ids: list[uuid.UUID], app_maker: async_sessionmaker[AsyncSession]
) -> int:
    discover(app.modules)  # importing the modules registers their scanners
    failed = 0
    for tenant_id in tenant_ids:
        try:
            async with tenant_session(app_maker, tenant_id) as db:
                await run_scanners(db, tenant_id)
        except Exception:  # one tenant's problem must not stop the others
            failed += 1
            log.exception("alerts job failed for a tenant", extra={"tenant_id": str(tenant_id)})
    return failed
