"""Raise, resolve and deliver alerts (FR-INV-012, FR-NTF-001).

Modules register a scanner that reports the conditions true right now for one type; `sync`
opens alerts for new conditions (and notifies the recipients once), and resolves alerts
whose condition is gone. Recipients come from the tenant's alert rules; with no rule for a
type, owners, co-owners and managers get it. Only members who can see the outlet are told."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipOutlet, Role
from app.core.notifications.models import Alert, Notification
from app.core.settings.models import AlertRule

DEFAULT_ROLES = ("owner", "co_owner", "manager")
KEEP_DAYS = 90  # docs/05 retention: notifications

Scanner = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]
_scanners: list[Scanner] = []


def register_scanner(scanner: Scanner) -> None:
    """Called once by a module at start-up (inventory registers its stock alerts)."""
    if scanner not in _scanners:
        _scanners.append(scanner)


@dataclass(frozen=True)
class Condition:
    outlet_id: uuid.UUID | None
    item_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)
    link: str | None = None

    @property
    def key(self) -> str:
        return ":".join(str(x or "-") for x in (self.outlet_id, self.item_id, self.batch_id))


async def recipients(
    db: AsyncSession, alert_type: str, outlet_id: uuid.UUID | None
) -> set[uuid.UUID]:
    rules = (
        await db.execute(
            select(AlertRule.recipient_role_id, AlertRule.recipient_user_id).where(
                AlertRule.alert_type == alert_type, AlertRule.channel == "in_app"
            )
        )
    ).all()
    role_ids = {r for r, _ in rules if r}
    user_ids = {u for _, u in rules if u}
    if not rules:
        stmt = select(Role.id).where(
            Role.template_key.in_(DEFAULT_ROLES), Role.tenant_id.is_not(None)
        )
        role_ids = set(await db.scalars(stmt))
    members = select(Membership.user_id).where(
        Membership.status == "active",
        or_(Membership.role_id.in_(role_ids), Membership.user_id.in_(user_ids)),
    )
    if outlet_id is not None:
        sees = exists().where(
            MembershipOutlet.membership_id == Membership.id, MembershipOutlet.outlet_id == outlet_id
        )
        members = members.where(or_(Membership.scope == "all", sees))
    return set(await db.scalars(members))


async def sync(
    db: AsyncSession, tenant_id: uuid.UUID, alert_type: str, now_true: list[Condition]
) -> tuple[int, int]:
    """Open alerts for new conditions, resolve the ones that cleared. Returns (opened, resolved)."""
    stmt = select(Alert).where(Alert.type == alert_type, Alert.state == "open")
    open_alerts = {a.key: a for a in await db.scalars(stmt)}
    current = {c.key: c for c in now_true}
    gone = [a.id for k, a in open_alerts.items() if k not in current]
    if gone:
        await db.execute(
            update(Alert)
            .where(Alert.id.in_(gone))
            .values(state="resolved", resolved_at=datetime.now(UTC))
        )
    new = [c for k, c in current.items() if k not in open_alerts]
    for c in new:
        alert = Alert(
            tenant_id=tenant_id,
            type=alert_type,
            key=c.key,
            outlet_id=c.outlet_id,
            item_id=c.item_id,
            batch_id=c.batch_id,
            details=c.details,
        )
        db.add(alert)
        await db.flush()
        users = await recipients(db, alert_type, c.outlet_id)
        if users:
            await db.execute(
                insert(Notification),
                [
                    {
                        "tenant_id": tenant_id,
                        "user_id": u,
                        "alert_id": alert.id,
                        "kind": alert_type,
                        "params": c.details,
                        "link": c.link,
                    }
                    for u in users
                ],
            )
    return len(new), len(gone)


async def run_scanners(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    for scanner in _scanners:
        await scanner(db, tenant_id)
    cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
    await db.execute(delete(Notification).where(Notification.created_at < cutoff))
