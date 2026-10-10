"""Sub-ledger totals for reconciliation (Gate 3, FR-FIN-005). The general ledger lives in
finance; stock, receivables and payables live in their own modules, which finance must not
read directly. So each module registers what its own records say an account role should
hold, and finance compares that with the books (like ledger invariants and demand)."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import TenantModule

Total = Callable[[AsyncSession], Awaitable[int]]


@dataclass(frozen=True)
class Subledger:
    module: str
    role: str  # the account role (system_key) it should match
    name: str  # stable key for the screen text
    total: Total


_registry: list[Subledger] = []


def register_subledger(module: str, role: str, name: str, total: Total) -> None:
    if all(s.name != name for s in _registry):
        _registry.append(Subledger(module, role, name, total))


async def subledgers(db: AsyncSession, tenant_id: uuid.UUID) -> list[tuple[Subledger, int]]:
    enabled = set(
        await db.scalars(
            select(TenantModule.module).where(
                TenantModule.tenant_id == tenant_id, TenantModule.enabled
            )
        )
    )
    return [(s, await s.total(db)) for s in _registry if s.module in enabled]
