"""Seed helpers for tests: a tenant with the default role templates and a subscription,
exactly as tenant creation will do it (slice 0.6). Seeds run as the owner role."""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.modules
from app.core.access.permissions import build_registry
from app.core.access.roles import create_tenant_roles
from app.core.ids import uuid7
from app.core.models import Membership, Subscription, Tenant, TenantModule, User
from app.core.modules import discover
from tests.conftest import TEST_OWNER_URL

REGISTRY = build_registry(discover(app.modules))


async def _run(fn: Any) -> Any:
    engine = create_async_engine(TEST_OWNER_URL)
    try:
        async with engine.connect() as conn, conn.begin():
            return await fn(AsyncSession(bind=conn))
    finally:
        await engine.dispose()


def seed_tenant(
    name: str = "Kitchen",
    *,
    plan_type: str = "free",
    ends_at: datetime | None = None,
    grace_days: int = 7,
    modules: tuple[str, ...] = (),
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Returns (tenant_id, role ids by template key)."""
    tenant_id = uuid7()

    async def go(db: AsyncSession) -> dict[str, uuid.UUID]:
        await db.execute(
            insert(Tenant).values(
                id=tenant_id,
                name=name,
                legal_name=name,
                country="ID",
                currency="IDR",
                language="id",
                timezone="Asia/Jakarta",
                profile="hybrid",
            )
        )
        await db.execute(
            insert(Subscription).values(
                tenant_id=tenant_id, plan_type=plan_type, ends_at=ends_at, grace_days=grace_days
            )
        )
        for module in modules:
            await db.execute(insert(TenantModule).values(tenant_id=tenant_id, module=module))
        await db.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        return await create_tenant_roles(db, tenant_id, REGISTRY)

    return tenant_id, asyncio.run(_run(go))


def add_member(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    password_hash: str,
    *,
    email: str | None = None,
    outlets: tuple[uuid.UUID, ...] | None = None,
) -> tuple[uuid.UUID, str]:
    """Create a user with a membership; `outlets` limits the scope. Returns (user_id, email)."""
    user_id = uuid7()
    email = email or f"user-{user_id}@example.test"

    async def go(db: AsyncSession) -> None:
        await db.execute(
            insert(User).values(id=user_id, email=email, name="U", password_hash=password_hash)
        )
        membership = uuid7()
        await db.execute(
            insert(Membership).values(
                id=membership,
                tenant_id=tenant_id,
                user_id=user_id,
                role_id=role_id,
                scope="outlets" if outlets is not None else "all",
            )
        )
        for outlet in outlets or ():
            await db.execute(
                text(
                    "INSERT INTO membership_outlets (tenant_id, membership_id, outlet_id) "
                    "VALUES (:t, :m, :o)"
                ),
                {"t": tenant_id, "m": membership, "o": outlet},
            )

    asyncio.run(_run(go))
    return user_id, email


def add_outlet(tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    outlet_id = uuid7()

    async def go(db: AsyncSession) -> None:
        await db.execute(
            text(
                "INSERT INTO outlets (id, tenant_id, name, type, timezone) "
                "VALUES (:i, :t, :n, 'branch', 'Asia/Jakarta')"
            ),
            {"i": outlet_id, "t": tenant_id, "n": name},
        )

    asyncio.run(_run(go))
    return outlet_id


def drop_tenant(tenant_id: uuid.UUID) -> None:
    async def go(db: AsyncSession) -> None:
        await db.execute(text("SET LOCAL session_replication_role = replica"))
        users = "SELECT user_id FROM memberships WHERE tenant_id = :t"
        for sql in (
            f"DELETE FROM sessions WHERE user_id IN ({users})",
            f"DELETE FROM recovery_codes WHERE user_id IN ({users})",
            f"DELETE FROM password_resets WHERE user_id IN ({users})",
            "DELETE FROM auth_throttle",
            "CREATE TEMP TABLE gone ON COMMIT DROP AS " + users,
            "DELETE FROM audit_log WHERE tenant_id = :t",
            "DELETE FROM invitations WHERE tenant_id = :t",
            "DELETE FROM tenant_settings WHERE tenant_id = :t",
            "DELETE FROM approval_rules WHERE tenant_id = :t",
            "DELETE FROM alert_rules WHERE tenant_id = :t",
            "DELETE FROM numbering_counters WHERE tenant_id = :t",
            "DELETE FROM stock_count_lines WHERE tenant_id = :t",
            "DELETE FROM stock_counts WHERE tenant_id = :t",
            "DELETE FROM adjustment_lines WHERE tenant_id = :t",
            "DELETE FROM adjustments WHERE tenant_id = :t",
            "DELETE FROM waste_lines WHERE tenant_id = :t",
            "DELETE FROM waste_logs WHERE tenant_id = :t",
            "DELETE FROM stock_movements WHERE tenant_id = :t",
            "DELETE FROM stock_balances WHERE tenant_id = :t",
            "DELETE FROM stock_batches WHERE tenant_id = :t",
            "DELETE FROM item_costs WHERE tenant_id = :t",
            "DELETE FROM bom_lines WHERE tenant_id = :t",
            "DELETE FROM boms WHERE tenant_id = :t",
            "DELETE FROM item_prices WHERE tenant_id = :t",
            "DELETE FROM channels WHERE tenant_id = :t",
            "DELETE FROM item_unit_conversions WHERE tenant_id = :t",
            "DELETE FROM item_translations WHERE tenant_id = :t",
            "DELETE FROM items WHERE tenant_id = :t",
            "DELETE FROM item_categories WHERE tenant_id = :t",
            "DELETE FROM units WHERE tenant_id = :t",
            "DELETE FROM idempotency_keys WHERE tenant_id = :t",
            "DELETE FROM membership_outlets WHERE tenant_id = :t",
            "DELETE FROM memberships WHERE tenant_id = :t",
            "DELETE FROM users WHERE id IN (SELECT user_id FROM gone)",
            "DELETE FROM role_permissions WHERE tenant_id = :t",
            "DELETE FROM roles WHERE tenant_id = :t",
            "DELETE FROM outlets WHERE tenant_id = :t",
            "DELETE FROM tenant_modules WHERE tenant_id = :t",
            "DELETE FROM subscriptions WHERE tenant_id = :t",
            "DELETE FROM tenants WHERE id = :t",
        ):
            await db.execute(text(sql), {"t": tenant_id})

    asyncio.run(_run(go))
