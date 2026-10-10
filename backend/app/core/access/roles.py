"""Copy the default role templates into a tenant (used when a tenant is created, slice 0.6)."""

import uuid

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.permissions import Registry
from app.core.ids import uuid7
from app.core.models import Role, RolePermission
from app.core.settings.models import ApprovalRule

# docs/03 section 7 defaults that need a role: "a manager approves a refund". Owners
# change or remove them in Settings > Approvals.
DEFAULT_APPROVALS = (("refund", 0, "manager"),)


async def create_tenant_roles(
    db: AsyncSession, tenant_id: uuid.UUID, registry: Registry
) -> dict[str, uuid.UUID]:
    """Insert one role per template with its permissions. Must run inside a tenant_session
    for `tenant_id`. Returns template key -> role id."""
    ids: dict[str, uuid.UUID] = {}
    for key, info in registry.template_info.items():
        role_id = uuid7()
        ids[key] = role_id
        await db.execute(
            insert(Role).values(
                id=role_id,
                tenant_id=tenant_id,
                name=info.name,
                template_key=key,
                requires_mfa=info.requires_mfa,
            )
        )
        codes = sorted(registry.templates[key])
        if codes:
            await db.execute(
                insert(RolePermission),
                [
                    {
                        "tenant_id": tenant_id,
                        "role_id": role_id,
                        "permission_code": c,
                        "limit_value": registry.default_limits.get(key, {}).get(c),
                    }
                    for c in codes
                ],
            )
    for document_type, min_amount, role_key in DEFAULT_APPROVALS:
        if role_key in ids:
            db.add(
                ApprovalRule(
                    tenant_id=tenant_id,
                    document_type=document_type,
                    min_amount=min_amount,
                    approver_role_id=ids[role_key],
                )
            )
    await db.flush()
    return ids


async def sync_new_permissions(db: AsyncSession, tenant_id: uuid.UUID, registry: Registry) -> int:
    """Grant permissions that are new to this tenant (a module released after it was created)
    to its template roles, as the template says. A permission any of the tenant's roles
    already holds is not new, so a default the owner removed is never granted again.
    Returns the number of grants added."""
    held = set(
        await db.scalars(
            select(RolePermission.permission_code).where(RolePermission.tenant_id == tenant_id)
        )
    )
    roles = (
        await db.execute(
            select(Role.id, Role.template_key).where(
                Role.tenant_id == tenant_id, Role.template_key.is_not(None)
            )
        )
    ).all()
    rows = [
        {
            "tenant_id": tenant_id,
            "role_id": role_id,
            "permission_code": code,
            "limit_value": registry.default_limits.get(key or "", {}).get(code),
        }
        for role_id, key in roles
        for code in sorted(registry.templates.get(key or "", frozenset()) - held)
    ]
    if rows:
        await db.execute(insert(RolePermission), rows)
    return len(rows)
