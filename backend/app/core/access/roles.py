"""Copy the default role templates into a tenant (used when a tenant is created, slice 0.6)."""

import uuid

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.permissions import Registry
from app.core.ids import uuid7
from app.core.models import Role, RolePermission


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
                [{"tenant_id": tenant_id, "role_id": role_id, "permission_code": c} for c in codes],
            )
    return ids
