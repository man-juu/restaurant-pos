"""Sign-in, sessions and lockout (FR-IDN-001, 003, 005, 007, 009; docs/06 section 3).

Sessions and throttle counters are global (not tenant-owned), so these functions take a plain
session without tenant context. Audit entries are written separately inside a tenant_session.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.models import AuthThrottle, User, UserSession

TOKEN_BYTES = 32  # 256-bit session tokens
TOUCH_INTERVAL = timedelta(minutes=1)  # write last_seen_at at most once a minute per session


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def throttle_key(kind: str, value: str) -> str:
    """Hashed so the table never stores emails or IPs in clear."""
    return f"{kind}:{hashlib.sha256(value.strip().lower().encode()).hexdigest()[:40]}"


@dataclass(frozen=True)
class MembershipInfo:
    tenant_id: uuid.UUID
    tenant_name: str
    membership_id: uuid.UUID
    role_id: uuid.UUID
    scope: str


async def active_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[MembershipInfo]:
    """Tenants the user can enter: active membership in an active tenant. Uses the narrow
    SECURITY DEFINER function because no tenant context exists yet at sign-in."""
    rows = await session.execute(
        text("SELECT * FROM auth_user_memberships(:uid)"), {"uid": user_id}
    )
    return [
        MembershipInfo(r.tenant_id, r.tenant_name, r.membership_id, r.role_id, r.scope)
        for r in rows
        if r.status == "active" and r.tenant_status == "active"
    ]


async def locked_until(session: AsyncSession, keys: list[str]) -> datetime | None:
    result = await session.execute(
        select(func.max(AuthThrottle.locked_until)).where(
            AuthThrottle.key.in_(keys), AuthThrottle.locked_until > func.now()
        )
    )
    return result.scalar_one_or_none()


_RECORD_FAILURE = text("""
    INSERT INTO auth_throttle AS t (key, failures, locked_until)
    VALUES (:key, 1, CASE WHEN :max <= 1 THEN now() + interval '30 seconds' END)
    ON CONFLICT (key) DO UPDATE SET
        failures = t.failures + 1,
        locked_until = CASE WHEN t.failures + 1 >= :max THEN now() + least(
            interval '30 seconds' * power(2, greatest(t.failures + 1 - :max, 0)),
            interval '15 minutes') END,
        updated_at = now()
""")


async def record_failure(session: AsyncSession, keys: list[str], max_failures: int) -> None:
    """Count a failure; from `max_failures` on, lock for 30 s, 60 s, 120 s ... up to 15 min.
    One atomic upsert per key, so parallel guesses cannot race past the limit."""
    for key in keys:
        await session.execute(_RECORD_FAILURE, {"key": key, "max": max_failures})


async def clear_failures(session: AsyncSession, keys: list[str]) -> None:
    await session.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(keys)))


async def find_user(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.strip()))
    return result.scalar_one_or_none()


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    ip: str | None,
    user_agent: str | None,
    settings: Settings,
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    row = UserSession(
        token_hash=hash_token(token),
        user_id=user_id,
        active_tenant_id=tenant_id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now().astimezone() + timedelta(hours=settings.session_absolute_hours),
        ip=ip,
        user_agent=(user_agent or "")[:256] or None,
    )
    session.add(row)
    await session.flush()
    return token, row


async def resolve_session(
    session: AsyncSession, token: str, settings: Settings
) -> UserSession | None:
    """Return the live session for a cookie token, enforcing revocation and both timeouts."""
    idle = timedelta(minutes=settings.session_idle_minutes)
    row = (
        await session.execute(
            select(UserSession).where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > func.now(),
                UserSession.last_seen_at > func.now() - idle,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.execute(
            update(UserSession)
            .where(
                UserSession.id == row.id,
                UserSession.last_seen_at < func.now() - TOUCH_INTERVAL,
            )
            .values(last_seen_at=func.now())
        )
    return row


async def revoke(session: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Revoke one of the user's own sessions. Effective on the very next request, because
    every request re-reads the session row."""
    result = await session.execute(
        update(UserSession)
        .where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def list_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[UserSession]:
    result = await session.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
        )
        .order_by(UserSession.last_seen_at.desc())
    )
    return list(result.scalars())
