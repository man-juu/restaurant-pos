"""Free AI image budget (ADR-022, FR-CAT-013).

Two guards, both checked before the provider is called:
1. Platform: all tenants share Cloudflare's free daily allowance. We stop at `ai_budget_percent`
   of it, so the provider's own limit is never reached (buffer for our estimate being low).
2. Tenant: at most `ai_tenant_daily_images` attempts per UTC day, so one tenant cannot use up
   everyone's allowance.

The budget is reserved in its own committed transaction before the slow external call, so two
concurrent requests can never both take the last slot. A failed call gives the platform budget
back; the attempt still counts for the tenant (stops retry loops)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.models import AiImageRequest, AiUsageDaily
from app.core.config import Settings
from app.core.errors import AppError


class AiDisabled(AppError):
    status_code, code = 409, "ai_disabled"


class AiLimitReached(AppError):
    status_code, code = 429, "ai_limit_reached"


class AiUsage(BaseModel):
    enabled: bool
    tenant_used: int
    tenant_limit: int
    remaining: int  # images this tenant can still make today (both guards applied)
    resets_at: datetime


@dataclass(frozen=True)
class Reservation:
    request_id: uuid.UUID
    day: date
    neurons: int


def _today() -> date:
    return datetime.now(UTC).date()


def _start(day: date) -> datetime:
    return datetime.combine(day, time(), UTC)


def _platform_limit(settings: Settings) -> int:
    return settings.ai_daily_free_neurons * settings.ai_budget_percent // 100


_RESERVE = text("""
    INSERT INTO ai_usage_daily (day, neurons, images) VALUES (:day, :cost, 1)
    ON CONFLICT (day) DO UPDATE
       SET neurons = ai_usage_daily.neurons + :cost, images = ai_usage_daily.images + 1
     WHERE ai_usage_daily.neurons + :cost <= :limit
    RETURNING neurons
""")


async def _tenant_used(db: AsyncSession, day: date) -> int:
    """Runs under RLS, so it counts only the current tenant's requests."""
    stmt = select(func.count()).where(AiImageRequest.created_at >= _start(day))
    return int(await db.scalar(stmt) or 0)


async def usage(db: AsyncSession, settings: Settings) -> AiUsage:
    day = _today()
    used = await _tenant_used(db, day)
    spent = await db.scalar(select(AiUsageDaily.neurons).where(AiUsageDaily.day == day)) or 0
    platform_left = max(_platform_limit(settings) - spent, 0) // settings.ai_neurons_per_image
    tenant_left = max(settings.ai_tenant_daily_images - used, 0)
    return AiUsage(
        enabled=settings.ai_enabled,
        tenant_used=used,
        tenant_limit=settings.ai_tenant_daily_images,
        remaining=min(platform_left, tenant_left) if settings.ai_enabled else 0,
        resets_at=_start(day + timedelta(days=1)),
    )


async def reserve(
    db: AsyncSession, settings: Settings, *, tenant_id: uuid.UUID, user_id: uuid.UUID, prompt: str
) -> Reservation:
    """Call inside its own tenant_session; it must commit before the provider call."""
    if not settings.ai_enabled:
        raise AiDisabled()
    day, cost = _today(), settings.ai_neurons_per_image
    # One request per tenant at a time decides the tenant cap (transaction-scoped lock).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"ai:{tenant_id}"}
    )
    if await _tenant_used(db, day) >= settings.ai_tenant_daily_images:
        raise AiLimitReached("tenant_daily_limit")
    limit = _platform_limit(settings)
    if (
        cost > limit
        or (await db.execute(_RESERVE, {"day": day, "cost": cost, "limit": limit})).first() is None
    ):
        raise AiLimitReached("platform_daily_limit")
    row = AiImageRequest(
        tenant_id=tenant_id, user_id=user_id, prompt=prompt, neurons=cost, succeeded=False
    )
    db.add(row)
    await db.flush()
    return Reservation(row.id, day, cost)


async def finish(db: AsyncSession, r: Reservation, *, upload_id: uuid.UUID | None) -> None:
    """Record the outcome; a failed call returns its share of the platform budget."""
    await db.execute(
        update(AiImageRequest)
        .where(AiImageRequest.id == r.request_id)
        .values(succeeded=upload_id is not None, upload_id=upload_id)
    )
    if upload_id is None:
        await db.execute(
            update(AiUsageDaily)
            .where(AiUsageDaily.day == r.day)
            .values(
                neurons=func.greatest(AiUsageDaily.neurons - r.neurons, 0),
                images=func.greatest(AiUsageDaily.images - 1, 0),
            )
        )
