"""Idempotency keys for create endpoints that clients may retry (FR-X-003).

Clients send `Idempotency-Key: <uuid>`. This slice validates the header and fingerprints the
request. Storage (`idempotency_keys`, unique on tenant_id + key, docs/05) needs tenant tables
and is added in slice 0.3: a repeat with the same body replays the stored response, a repeat
with a different body returns 409 `idempotency_key_reused`.
"""

import hashlib
import uuid
from typing import Annotated

from fastapi import Header, Request

from app.core.errors import AppError


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
