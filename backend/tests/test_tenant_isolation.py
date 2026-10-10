"""FR-TEN-001/002 and CLAUDE.md rule 1: tenant A can never see or write tenant B's data,
and with no tenant set nothing is visible. Runs as the restricted app role."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.ids import uuid7
from app.core.models import AuditLog, Membership, Outlet, Role, Tenant, User
from app.core.tenancy import tenant_session

pytestmark = pytest.mark.anyio

TENANT_TABLES = (Tenant, Outlet, Role, Membership, AuditLog)


@dataclass
class World:
    a: uuid.UUID
    b: uuid.UUID
    outlet_b: uuid.UUID


@pytest.fixture
async def world(owner_engine: AsyncEngine) -> AsyncIterator[World]:
    """Two tenants with an outlet, a role, a member and an audit entry each, plus a template
    role. Seeded as the owner, removed afterwards (audit rows bypass the trigger via
    session_replication_role, available to the superuser only)."""
    a, b, template = uuid7(), uuid7(), uuid7()
    outlets = {a: uuid7(), b: uuid7()}
    async with owner_engine.begin() as conn:
        await conn.execute(
            insert(Role),
            [{"id": template, "tenant_id": None, "name": f"t-{template}", "is_template": True}],
        )
        for tenant in (a, b):
            user, role = uuid7(), uuid7()
            await conn.execute(
                insert(Tenant).values(
                    id=tenant,
                    name="T",
                    legal_name="T",
                    country="ID",
                    currency="IDR",
                    language="id",
                    timezone="Asia/Jakarta",
                    profile="cloud_kitchen",
                )
            )
            await conn.execute(
                insert(Outlet).values(
                    id=outlets[tenant],
                    tenant_id=tenant,
                    name="O",
                    type="cloud_kitchen",
                    timezone="Asia/Jakarta",
                )
            )
            await conn.execute(insert(User).values(id=user, email=f"{user}@example.test", name="U"))
            await conn.execute(insert(Role).values(id=role, tenant_id=tenant, name="Manager"))
            await conn.execute(
                insert(Membership).values(tenant_id=tenant, user_id=user, role_id=role)
            )
            await conn.execute(insert(AuditLog).values(tenant_id=tenant, action="test.seeded"))
    yield World(a=a, b=b, outlet_b=outlets[b])
    async with owner_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        for t in (
            "audit_log",
            "memberships",
            "membership_outlets",
            "outlets",
            "role_permissions",
            "idempotency_keys",
        ):
            await conn.execute(
                text(f"DELETE FROM {t} WHERE tenant_id = ANY(:ids)"), {"ids": [a, b]}
            )
        await conn.execute(
            text("DELETE FROM roles WHERE tenant_id = ANY(:ids) OR id = :t"),
            {"ids": [a, b], "t": template},
        )
        await conn.execute(text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": [a, b]})


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_fr_ten_001_tenant_sees_only_its_own_rows(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_session(sessions, world.a) as s:
        for model in TENANT_TABLES:
            column = Tenant.id if model is Tenant else model.tenant_id  # type: ignore[union-attr]
            seen = set((await s.execute(select(column).distinct())).scalars())
            assert world.b not in seen, model.__tablename__
            assert world.a in seen, model.__tablename__


async def test_fr_ten_002_cannot_insert_row_for_another_tenant(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(sessions, world.a) as s:
            await s.execute(
                insert(Outlet).values(
                    tenant_id=world.b, name="sneaky", type="branch", timezone="Asia/Jakarta"
                )
            )


async def test_cannot_update_another_tenants_row(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_session(sessions, world.a) as s:
        result = await s.execute(
            update(Outlet).where(Outlet.id == world.outlet_b).values(name="hijacked")
        )
        assert result.rowcount == 0  # type: ignore[attr-defined]


async def test_cannot_move_own_row_to_another_tenant(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(sessions, world.a) as s:
            await s.execute(
                update(Outlet).where(Outlet.tenant_id == world.a).values(tenant_id=world.b)
            )


async def test_no_tenant_context_returns_zero_rows(world: World, engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        for model in TENANT_TABLES:
            count = (await conn.execute(select(func.count()).select_from(model))).scalar()
            if model is Role:  # platform templates are shared and readable by design
                count = (
                    await conn.execute(select(func.count()).where(Role.tenant_id.is_not(None)))
                ).scalar()
            assert count == 0, model.__tablename__


async def test_tenant_setting_does_not_leak_to_next_transaction(
    world: World, settings: object
) -> None:
    """Pooled connections are reused: the tenant must vanish when the transaction ends."""
    from app.core.db import create_engine

    one_conn = create_engine(settings.model_copy(update={"db_pool_size": 1}))  # type: ignore[attr-defined]
    sessions = async_sessionmaker(one_conn)
    try:
        async with tenant_session(sessions, world.a) as s:
            assert (await s.execute(select(func.count()).select_from(Outlet))).scalar() == 1
        async with sessions() as s:  # same pooled connection, new transaction, no context
            assert (await s.execute(select(func.count()).select_from(Outlet))).scalar() == 0
    finally:
        await one_conn.dispose()


async def test_templates_readable_but_not_writable(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_session(sessions, world.a) as s:
        templates = (await s.execute(select(func.count()).where(Role.is_template))).scalar_one()
        assert templates >= 1
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(sessions, world.a) as s:
            await s.execute(
                insert(Role).values(tenant_id=None, name="evil template", is_template=True)
            )


async def test_fr_aud_002_audit_log_is_append_only(
    world: World, owner_engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_session(sessions, world.a) as s:
        await s.execute(insert(AuditLog).values(tenant_id=world.a, action="test.inserted"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with tenant_session(sessions, world.a) as s:
            await s.execute(text("UPDATE audit_log SET action = 'x'"))
    # Even the owner is stopped by the trigger.
    with pytest.raises(DBAPIError, match="append-only"):
        async with owner_engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log WHERE tenant_id = :t"), {"t": world.a})


async def test_fr_x_003_idempotency_replay_and_reuse(
    world: World, sessions: async_sessionmaker[AsyncSession], owner_engine: AsyncEngine
) -> None:
    from app.core.errors import ConflictError
    from app.core.idempotency import StoredResponse, remember, replay_or_none

    key = uuid.uuid4()
    async with tenant_session(sessions, world.a) as s:
        assert await replay_or_none(s, key, "hash-1") is None
        await remember(s, world.a, key, "hash-1", 201, {"id": "x"})
    async with tenant_session(sessions, world.a) as s:
        assert await replay_or_none(s, key, "hash-1") == StoredResponse(201, {"id": "x"})
        with pytest.raises(ConflictError):
            await replay_or_none(s, key, "hash-2")
    # The same key is independent per tenant.
    async with tenant_session(sessions, world.b) as s:
        assert await replay_or_none(s, key, "hash-1") is None
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM idempotency_keys WHERE key = :k"), {"k": key})
