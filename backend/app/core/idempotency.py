"""Idempotency keys for create endpoints that clients may retry (FR-X-003).

Clients send `Idempotency-Key: <uuid>`. A create endpoint calls `replay_or_none` first: a
repeat with the same request returns the stored response, a repeat with a different request is
rejected with 409 `idempotency_key_reused`. After doing the work it calls `remember` in the
same transaction, so the result and the key commit together or not at all.
"""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Header, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError
from app.core.logging import user_id_var
from app.core.models import IdempotencyKey


class InvalidIdempotencyKey(AppError):
    status_code, code = 400, "invalid_idempotency_key"


async def idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> uuid.UUID | None:
    """Optional key. Use `RequiredIdempotencyKey` on endpoints where retries are expected."""
    if key is None:
        return None
    try:
        return uuid.UUID(key)
    except ValueError:
        raise InvalidIdempotencyKey() from None


async def required_idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> uuid.UUID:
    parsed = await idempotency_key(key)
    if parsed is None:
        raise InvalidIdempotencyKey(details={"reason": "missing"})
    return parsed


async def request_fingerprint(request: Request) -> str:
    """SHA-256 of method, path and body: detects a key reused for a different request."""
    body = await request.body()
    digest = hashlib.sha256()
    for part in (request.method.encode(), request.url.path.encode(), body):
        digest.update(len(part).to_bytes(8, "big") + part)
    return digest.hexdigest()


def _bound(request_hash: str) -> str:
    """The fingerprint tied to the signed-in user of the current tenant session (security
    review 2l): another user who learns a key cannot replay someone else's stored answer."""
    user = user_id_var.get() or ""
    return hashlib.sha256(f"{user}:{request_hash}".encode()).hexdigest()


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: Any


async def replay_or_none(
    session: AsyncSession, key: uuid.UUID, request_hash: str
) -> StoredResponse | None:
    """Return the stored response for a retried request, or None if the key is new.
    Runs inside `tenant_session`, so RLS limits the lookup to the current tenant."""
    row = (
        await session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == key).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.response_status is None:
        return None
    if row.request_hash != _bound(request_hash):
        raise ConflictError("idempotency_key_reused")
    return StoredResponse(row.response_status, row.response_body)


async def remember(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    key: uuid.UUID,
    request_hash: str,
    status: int,
    body: Any,
) -> None:
    """Store the response in the caller's transaction. If a concurrent request with the same
    key committed first, the unique (tenant_id, key) constraint makes this one fail and roll
    back, so the work is never done twice."""
    await session.execute(
        insert(IdempotencyKey).values(
            tenant_id=tenant_id,
            key=key,
            request_hash=_bound(request_hash),
            response_status=status,
            response_body=body,
        )
    )
