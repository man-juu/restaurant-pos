"""Ledger invariants (docs/05 section 5, I-1 to I-4), checked nightly per tenant.

Each module registers the checks over its own tables; a check returns how many rows break
the rule (0 = holds). The job records breaks for the platform admin (job_failures), because
a broken invariant is a bug to fix, not something a tenant can act on."""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

Check = Callable[[AsyncSession], Awaitable[int]]
_checks: dict[str, Check] = {}


def register_invariant(name: str, check: Check) -> None:
    _checks[name] = check


async def run_checks(db: AsyncSession, _tenant_id: uuid.UUID) -> dict[str, int]:
    """Broken invariants for the tenant of the session: name -> rows that break it."""
    out = {}
    for name, check in sorted(_checks.items()):
        if broken := await check(db):
            out[name] = broken
    return out
