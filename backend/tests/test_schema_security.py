"""CLAUDE.md rule 1: these tests fail if any tenant table lacks RLS, FORCE, a policy or a
leading tenant_id index, or if the app role is too powerful. They scan the live schema, so a
new table added without the helper fails CI automatically."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.anyio

RLS_FLAGS = "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'tenants'"
APP_ROLE_FLAGS = (
    "SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname = 'pos_app'"
)

TENANT_TABLES = text("""
    SELECT c.relname AS table, c.relrowsecurity AS rls, c.relforcerowsecurity AS force,
           (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies,
           EXISTS (
               SELECT 1 FROM pg_index i
               JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
               WHERE i.indrelid = c.oid AND a.attname = 'tenant_id'
           ) AS leading_index
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
                  AND a.attname = 'tenant_id' AND NOT a.attisdropped)
""")


async def test_every_tenant_table_has_forced_rls_policy_and_index(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as conn:
        rows = (await conn.execute(TENANT_TABLES)).mappings().all()
    assert len(rows) >= 7  # guard: the query must actually find the tenant tables
    problems = [
        f"{r['table']}: rls={r['rls']} force={r['force']} policies={r['policies']} "
        f"leading_tenant_index={r['leading_index']}"
        for r in rows
        if not (r["rls"] and r["force"] and r["policies"] and r["leading_index"])
    ]
    assert problems == []


async def test_tenants_table_is_isolated_by_id(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        row = (await conn.execute(text(RLS_FLAGS))).one()
    assert row == (True, True)


async def test_app_role_cannot_bypass_rls(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        role = (await conn.execute(text(APP_ROLE_FLAGS))).one()
        owned = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_tables "
                    "WHERE schemaname = 'public' AND tableowner = 'pos_app'"
                )
            )
        ).scalar()
    assert role == (False, False, False)
    assert owned == 0


async def test_fr_aud_002_app_role_cannot_change_audit_log(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        privileges = {
            p: (
                await conn.execute(
                    text("SELECT has_table_privilege('pos_app', 'audit_log', :p)"), {"p": p}
                )
            ).scalar()
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
        }
    assert privileges == {
        "SELECT": True,
        "INSERT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    }
