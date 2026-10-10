"""Web push (FR-NTF-005). Browsers hand over a subscription (a push service URL plus keys);
the worker sends one short, encrypted message per person when they have new notifications:
"you have N new notifications" and the app link, never the details (they stay in the app).

Security: the server calls the subscription URL, so only HTTPS URLs on the known browser push
services are accepted (no request to an internal or arbitrary host). Dead subscriptions (404,
410) are removed; others are dropped after repeated failures."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.notifications.models import Notification
from app.core.notifications.push_models import PushSubscription

log = logging.getLogger(__name__)
PUSH_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Edge on Android, most Android browsers
    "updates.push.services.mozilla.com",  # Firefox
    "push.services.mozilla.com",
    ".push.apple.com",  # Safari, iOS home-screen apps
    ".notify.windows.com",  # Edge on Windows
)
MAX_FAILURES = 5
LOOKBACK = timedelta(hours=6)  # older unsent notifications are not pushed any more


class BadEndpoint(AppError):
    status_code, code = 422, "push_endpoint_not_allowed"


def allowed_endpoint(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.port not in (None, 443):
        return False
    return any(
        host == h.lstrip(".") or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS
    )


async def subscribe(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> None:
    if not allowed_endpoint(endpoint):
        raise BadEndpoint()
    stmt = insert(PushSubscription).values(
        tenant_id=tenant_id, user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth_secret=auth
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["tenant_id", "endpoint"],
            set_={"user_id": user_id, "p256dh": p256dh, "auth_secret": auth, "failures": 0},
        )
    )


async def unsubscribe(db: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
        )
    )


def _send(sub: PushSubscription, payload: str, settings: Settings) -> int:
    """One push; returns the HTTP status (0 when the service could not be reached)."""
    try:
        webpush(
            {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth_secret}},
            payload,
            vapid_private_key=Vapid01.from_raw(settings.vapid_private_key.encode()),
            vapid_claims={"sub": settings.vapid_subject},
            ttl=12 * 3600,
            timeout=10,
        )
        return 201
    except WebPushException as err:
        return err.response.status_code if err.response is not None else 0


async def _deliver(db: AsyncSession, sub: PushSubscription, payload: str, s: Settings) -> None:
    status = await asyncio.to_thread(_send, sub, payload, s)
    if status in (404, 410):  # the browser unsubscribed
        await db.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
    elif 200 <= status < 300:
        sub.last_ok_at, sub.failures = datetime.now(UTC), 0
    elif sub.failures + 1 >= MAX_FAILURES:
        await db.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
    else:
        sub.failures += 1


async def push_new(db: AsyncSession, settings: Settings) -> int:
    """Worker task, per tenant: push each person's new notifications once. Returns pushes."""
    if not settings.push_enabled:
        return 0
    since = datetime.now(UTC) - LOOKBACK
    rows = list(
        await db.execute(
            select(Notification.user_id, Notification.link).where(
                Notification.pushed_at.is_(None),
                Notification.read_at.is_(None),
                Notification.created_at >= since,
            )
        )
    )
    if not rows:
        return 0
    per_user: dict[uuid.UUID, list[str | None]] = {}
    for user_id, link in rows:
        per_user.setdefault(user_id, []).append(link)
    subs = await db.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(per_user)))
    sent = 0
    for sub in subs:
        links = per_user[sub.user_id]
        payload = json.dumps({"count": len(links), "link": links[-1] or "/notifications"})
        await _deliver(db, sub, payload, settings)
        sent += 1
    await db.execute(
        update(Notification)
        .where(Notification.pushed_at.is_(None), Notification.user_id.in_(per_user))
        .values(pushed_at=datetime.now(UTC))
    )
    return sent
