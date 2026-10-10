"""Append-only audit log writer (FR-AUD-001, CLAUDE.md rule 7).

Call it inside the same `tenant_session` transaction as the action it records, so the action
and its audit entry commit together. `summary` must not contain passwords, tokens or other
secrets; keep it to what changed.
"""

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_var
from app.core.models import AuditLog


async def record(  # noqa: PLR0913 - keyword-only audit fields
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None = None,
    actor_type: str = "user",
    outlet_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    summary: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    await session.execute(
        insert(AuditLog).values(
            tenant_id=tenant_id,
            action=action,
            user_id=user_id,
            actor_type=actor_type,
            outlet_id=outlet_id,
            target_type=target_type,
            target_id=target_id,
            summary=summary or {},
            request_id=request_id_var.get(),
            ip=ip,
        )
    )
