"""A member's own limit on a permission (docs/03 rule 7), for checks made later than the
request of the person who set something: for example a discount checked again at payment
against the limit of whoever gave it."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NO_GRANT = -1  # the person no longer holds the permission at all

_SQL = text("""
    SELECT rp.limit_value FROM memberships m
    JOIN role_permissions rp ON rp.role_id = m.role_id AND rp.permission_code = :code
    WHERE m.user_id = :user_id AND m.status = 'active'
""")


async def limit_of(db: AsyncSession, user_id: uuid.UUID | None, permission: str) -> int | None:
    """The limit (None = no limit), or NO_GRANT. Runs under the tenant's RLS session."""
    if user_id is None:
        return NO_GRANT
    row = (await db.execute(_SQL, {"user_id": user_id, "code": permission})).first()
    return NO_GRANT if row is None else row[0]
