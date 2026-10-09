"""Alerts job (docs/04 section 10): for every active tenant, run the registered alert
scanners in that tenant's own RLS context, one transaction per tenant, so one tenant's
failure never touches another's data. The platform role only lists tenants."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules
from app.admin.models import JobFailure
from app.core.invariants import run_checks
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
) -> dict[uuid.UUID, str]:
    """Returns the tenants that failed, with the error type (the caller records them)."""
    discover(app.modules)  # importing the modules registers their scanners
    failed: dict[uuid.UUID, str] = {}
    for tenant_id in tenant_ids:
        try:
            async with tenant_session(app_maker, tenant_id) as db:
                await run_scanners(db, tenant_id)
        except Exception as err:  # one tenant's problem must not stop the others
            failed[tenant_id] = type(err).__name__
            log.exception("alerts job failed for a tenant", extra={"tenant_id": str(tenant_id)})
    return failed


async def record_failures(admin_db: AsyncSession, job: str, failed: dict[uuid.UUID, str]) -> None:
    """FR-ADM-004: what the usage overview counts. Error type only, no data."""
    admin_db.add_all(JobFailure(job=job, tenant_id=t, error=e[:200]) for t, e in failed.items())
    await admin_db.flush()


async def run_invariants(
    tenant_ids: list[uuid.UUID], app_maker: async_sessionmaker[AsyncSession]
) -> dict[uuid.UUID, str]:
    """Nightly (docs/05 rule 2): broken invariants per tenant, as text for job_failures."""
    discover(app.modules)
    broken: dict[uuid.UUID, str] = {}
    for tenant_id in tenant_ids:
        async with tenant_session(app_maker, tenant_id) as db:
            found = await run_checks(db, tenant_id)
        if found:
            broken[tenant_id] = "; ".join(f"{k}: {v}" for k, v in found.items())
            log.error("ledger invariant broken", extra={"tenant_id": str(tenant_id)})
    return broken
