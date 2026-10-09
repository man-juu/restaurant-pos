"""Feature flags per tenant (FR-ADM-006) for staged rollouts.

The registry below is the list of flags and their default; the platform admin can turn a
flag on or off for one tenant (a row in tenant_flags overrides the default). Code asks
`flag_on`; the UI gets the enabled set through /me/capabilities."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at

# name -> (default, what it does). Add a flag here before using it anywhere.
FLAGS: dict[str, tuple[bool, str]] = {
    "ai_images": (True, "Free AI images for item photos (ADR-022)"),
    "reports_export": (True, "CSV and Excel downloads of reports"),
}


class TenantFlag(Base):
    __tablename__ = "tenant_flags"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    flag: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column()
    updated_at: Mapped[datetime] = _created_at()


def overrides_subquery() -> Any:
    """The tenant's overrides as one JSON object, to fold into another query (one round trip)."""
    agg = func.json_object_agg(TenantFlag.flag, TenantFlag.enabled)
    return select(func.coalesce(agg, text("'{}'::json"))).scalar_subquery()


def resolve(overrides: dict[str, bool]) -> set[str]:
    return {name for name, (default, _) in FLAGS.items() if overrides.get(name, default)}


async def enabled_flags(db: AsyncSession) -> set[str]:
    """Flags on for the tenant of the current session (RLS)."""
    return resolve(dict((await db.execute(select(TenantFlag.flag, TenantFlag.enabled))).all()))


async def flag_on(db: AsyncSession, name: str) -> bool:
    if name not in FLAGS:
        raise KeyError(name)
    return name in await enabled_flags(db)
