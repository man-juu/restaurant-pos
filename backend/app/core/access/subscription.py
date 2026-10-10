"""Subscription state (FR-SUB-001 to 004).

The effective state is computed from the dates on every request instead of trusting a stored
status that a nightly job must keep current: if the job is late, access still ends on time.
`suspended` is the only manual state (set by the platform admin, FR-SUB-005).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

WRITE_BLOCKED = frozenset({"read_only", "suspended"})


@dataclass(frozen=True)
class SubscriptionInfo:
    plan_type: str  # "free" or "paid"
    ends_at: datetime | None
    grace_days: int
    reminders_enabled: bool
    reminder_days: tuple[int, ...]
    suspended: bool


def effective_state(sub: SubscriptionInfo | None, now: datetime) -> str:
    """free | active | expiring | grace | read_only | suspended."""
    if sub is None:
        return "read_only"  # fail closed: a tenant without a subscription row cannot write
    if sub.suspended:
        return "suspended"
    if sub.plan_type == "free":
        return "free"
    return _paid_state(sub, now)


def _paid_state(sub: SubscriptionInfo, now: datetime) -> str:
    if sub.ends_at is None:
        return "active"
    if now >= sub.ends_at + timedelta(days=sub.grace_days):
        return "read_only"
    if now >= sub.ends_at:
        return "grace"
    if sub.reminder_days and now >= sub.ends_at - timedelta(days=max(sub.reminder_days)):
        return "expiring"
    return "active"


def days_left(sub: SubscriptionInfo, now: datetime) -> int | None:
    if sub.ends_at is None:
        return None
    return max((sub.ends_at - now).days, 0)
