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

from app.core.models import Membership, MembershipOutlet, Role, RolePermission
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


async def members(
    db: AsyncSession,
    outlet_id: uuid.UUID | None,
    *,
    role_ids: set[uuid.UUID],
    user_ids: set[uuid.UUID] | None = None,
    permission: str | None = None,
) -> set[uuid.UUID]:
    """Active members with one of the roles (or listed by user) who can see the outlet and,
    when given, hold `permission` (owners and co-owners hold every permission)."""
    stmt = select(Membership.user_id).where(
        Membership.status == "active",
        or_(Membership.role_id.in_(role_ids), Membership.user_id.in_(user_ids or set())),
    )
    if outlet_id is not None:
        sees = exists().where(
            MembershipOutlet.membership_id == Membership.id, MembershipOutlet.outlet_id == outlet_id
        )
        stmt = stmt.where(or_(Membership.scope == "all", sees))
    if permission is not None:
        holds = exists().where(
            RolePermission.role_id == Membership.role_id,
            RolePermission.permission_code == permission,
        )
        everything = exists().where(
            Role.id == Membership.role_id, Role.template_key.in_(("owner", "co_owner"))
        )
        stmt = stmt.where(or_(holds, everything))
    return set(await db.scalars(stmt))


async def recipients(
    db: AsyncSession,
    alert_type: str,
    outlet_id: uuid.UUID | None,
    permission: str | None = None,
    *,
    any_role: bool = False,
) -> set[uuid.UUID]:
    """Who gets `alert_type`: the alert rules, or by default the owner, co-owner and manager
    roles (`any_role`: every role holding `permission`, e.g. the central kitchen's store)."""
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
        stmt = select(Role.id).where(Role.tenant_id.is_not(None))
        if not any_role:
            stmt = stmt.where(Role.template_key.in_(DEFAULT_ROLES))
        role_ids = set(await db.scalars(stmt))
    return await members(db, outlet_id, role_ids=role_ids, user_ids=user_ids, permission=permission)


async def notify(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    users: set[uuid.UUID],
    kind: str,
    params: dict[str, Any],
    link: str | None,
    alert_id: uuid.UUID | None = None,
) -> None:
    """One notification per user (events such as an approval request, or a new alert)."""
    if not users:
        return
    await db.execute(
        insert(Notification),
        [
            {
                "tenant_id": tenant_id,
                "user_id": u,
                "alert_id": alert_id,
                "kind": kind,
                "params": params,
                "link": link,
            }
            for u in users
        ],
    )


async def sync(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    alert_type: str,
    now_true: list[Condition],
    permission: str | None = None,
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
        users = await recipients(db, alert_type, c.outlet_id, permission)
        await notify(db, tenant_id, users, alert_type, c.details, c.link, alert.id)
    return len(new), len(gone)


async def run_scanners(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    for scanner in _scanners:
        await scanner(db, tenant_id)
    cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
    await db.execute(delete(Notification).where(Notification.created_at < cutoff))
