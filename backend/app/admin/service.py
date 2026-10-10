"""Platform admin operations on tenants (FR-ADM-001, FR-ADM-003, FR-SUB-001/002/003/005).

Runs on the admin engine (role pos_admin). Every action writes an audit entry into the
tenant's own audit log with actor_type="admin", so the tenant owner sees what the platform did
(FR-AUD-003).
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Impersonation
from app.admin.security import AdminContext
from app.core.access.permissions import Registry, build_registry
from app.core.access.roles import create_tenant_roles, sync_new_permissions
from app.core.access.subscription import SubscriptionInfo, effective_state
from app.core.identity import service as identity
from app.core.logging import request_id_var
from app.core.models import (
    AuditLog,
    Invitation,
    Membership,
    Role,
    Subscription,
    Tenant,
    TenantModule,
)
from app.core.module_catalog import PROFILE_DEFAULTS, validate_module_set
from app.core.modules import discover
from app.core.notifications.models import Notification


async def audit_admin(
    db: AsyncSession,
    admin: AdminContext | None,
    tenant_id: uuid.UUID,
    action: str,
    summary: dict[str, Any] | None = None,
) -> None:
    await db.execute(
        insert(AuditLog).values(
            tenant_id=tenant_id,
            action=action,
            actor_type="admin" if admin else "system",
            target_type="tenant",
            target_id=tenant_id,
            summary={**(summary or {}), **({"admin": admin.email} if admin else {})},
            request_id=request_id_var.get(),
        )
    )


async def set_tenant_context(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Role creation reuses the tenant-side helper, whose RLS WITH CHECK still applies."""
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})


async def create_tenant(
    db: AsyncSession,
    admin: AdminContext,
    registry: Registry,
    *,
    fields: dict[str, Any],
    owner_email: str,
    plan_type: str,
    ends_at: datetime | None,
    invitation_ttl_hours: int,
) -> tuple[uuid.UUID, str]:
    """Tenant + subscription + profile modules + role templates + owner invitation.
    Returns (tenant_id, invitation token)."""
    tenant = Tenant(**fields)
    db.add(tenant)
    await db.flush()
    await set_tenant_context(db, tenant.id)
    db.add(Subscription(tenant_id=tenant.id, plan_type=plan_type, ends_at=ends_at))
    modules = set(PROFILE_DEFAULTS[tenant.profile])
    validate_module_set(modules)
    for module in sorted(modules):
        db.add(TenantModule(tenant_id=tenant.id, module=module))
    roles = await create_tenant_roles(db, tenant.id, registry)
    token = secrets.token_urlsafe(32)
    db.add(
        Invitation(
            tenant_id=tenant.id,
            email=owner_email,
            role_id=roles["owner"],
            invited_by=None,
            token_hash=identity.hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=invitation_ttl_hours),
        )
    )
    await audit_admin(
        db,
        admin,
        tenant.id,
        "admin.tenant_created",
        {"profile": tenant.profile, "owner_email": owner_email},
    )
    return tenant.id, token


async def set_modules(
    db: AsyncSession, admin: AdminContext, tenant_id: uuid.UUID, modules: Sequence[str]
) -> None:
    wanted = set(modules)
    validate_module_set(wanted)
    rows = (
        await db.execute(select(TenantModule).where(TenantModule.tenant_id == tenant_id))
    ).scalars()
    current = {r.module: r for r in rows}
    for name, row in current.items():  # disabling keeps the data (FR-TEN-003)
        row.enabled = name in wanted
    for name in wanted - current.keys():
        db.add(TenantModule(tenant_id=tenant_id, module=name))
    await audit_admin(db, admin, tenant_id, "admin.modules_changed", {"modules": sorted(wanted)})


async def set_subscription(
    db: AsyncSession, admin: AdminContext, tenant_id: uuid.UUID, values: dict[str, Any]
) -> None:
    sub = (
        await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
    ).scalar_one()
    before = {k: _plain(getattr(sub, k)) for k in values}
    for key, value in values.items():
        setattr(sub, key, value)
    await audit_admin(
        db,
        admin,
        tenant_id,
        "admin.subscription_changed",
        {"before": before, "after": {k: _plain(v) for k, v in values.items()}},
    )


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


async def set_status(
    db: AsyncSession, admin: AdminContext, tenant_id: uuid.UUID, status: str
) -> None:
    """suspend / reactivate / delete (soft: data kept until the purge process, docs/05)."""
    await db.execute(update(Tenant).where(Tenant.id == tenant_id).values(status=status))
    await db.execute(
        update(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .values(suspended=status != "active")
    )
    await audit_admin(db, admin, tenant_id, f"admin.tenant_{status}")


async def start_impersonation(
    db: AsyncSession, admin: AdminContext, tenant_id: uuid.UUID, reason: str, minutes: int
) -> Impersonation:
    imp = Impersonation(
        admin_id=admin.admin_id,
        tenant_id=tenant_id,
        reason=reason,
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )
    db.add(imp)
    await db.flush()
    await audit_admin(
        db,
        admin,
        tenant_id,
        "admin.impersonation_started",
        {"reason": reason, "minutes": minutes, "impersonation_id": str(imp.id)},
    )
    return imp


async def run_subscription_job(db: AsyncSession, now: datetime) -> list[tuple[uuid.UUID, str, str]]:
    """Daily job (FR-SUB-002/003): record each tenant's state transitions in its audit log.
    Access itself never waits for this job: requests compute the state from the dates.
    Returns (tenant_id, from, to) for each transition; `now` is injected for tests."""
    changes = []
    subs = (await db.execute(select(Subscription))).scalars().all()
    for sub in subs:
        state = effective_state(
            SubscriptionInfo(
                sub.plan_type,
                sub.ends_at,
                sub.grace_days,
                sub.reminders_enabled,
                tuple(sub.reminder_days or ()),
                sub.suspended,
            ),
            now,
        )
        if state != sub.last_state:
            changes.append((sub.tenant_id, sub.last_state or "new", state))
            await audit_admin(
                db,
                None,
                sub.tenant_id,
                "subscription.state_changed",
                {"from": sub.last_state, "to": state, "at": now.isoformat()},
            )
            await _notify_owners(db, sub.tenant_id, state)
            sub.last_state = state
    return changes


async def _notify_owners(db: AsyncSession, tenant_id: uuid.UUID, state: str) -> None:
    """FR-SUB-006: owners and co-owners see the new subscription state in the app."""
    stmt = (
        select(Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
            Role.template_key.in_(("owner", "co_owner")),
        )
    )
    users = set(await db.scalars(stmt))
    if users:
        await db.execute(
            insert(Notification),
            [
                {
                    "tenant_id": tenant_id,
                    "user_id": u,
                    "kind": "subscription_state",
                    "params": {"state": state},
                    "link": "/settings",
                }
                for u in users
            ],
        )


async def sync_roles(db: AsyncSession) -> int:
    """`sync-roles` command: new module permissions for every existing tenant (see
    app.core.access.roles.sync_new_permissions for why removed defaults stay removed)."""
    import app.modules  # the module registry, as the API builds it

    registry = build_registry(discover(app.modules))
    added = 0
    for tenant_id in list(await db.scalars(select(Tenant.id))):
        added += await sync_new_permissions(db, tenant_id, registry)
    return added
