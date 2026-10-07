"""SQL helpers for migrations. Kept inside migrations/ so old revisions never change when
application code does."""

from alembic import op

APP_ROLE = "pos_app"  # what the API connects as: not superuser, not table owner
READONLY_ROLE = "pos_readonly"  # reporting and support queries
# Owns the few SECURITY DEFINER functions that must look across tenants (sign-in needs "which
# tenants does this user belong to" before any tenant is chosen). NOLOGIN: nobody connects as it.
AUTH_ROLE = "pos_auth"

_CURRENT_TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"


def ensure_roles() -> None:
    """Create the NOLOGIN roles if missing. Login and passwords are set outside migrations
    (infra/db/init in dev, the server runbook in production), so no secret lives in Git."""
    for role in (APP_ROLE, READONLY_ROLE):
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
            f"THEN CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}, {READONLY_ROLE}")


def grant(table: str, app_privileges: str) -> None:
    """Explicit grants per table (deny by default; no ALTER DEFAULT PRIVILEGES)."""
    op.execute(f"GRANT {app_privileges} ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON {table} TO {READONLY_ROLE}")


def enable_tenant_rls(
    table: str, column: str = "tenant_id", *, readable_templates: bool = False
) -> None:
    """ENABLE + FORCE row-level security with a policy on the current tenant (docs/05 section 4).

    FORCE matters: without it the table owner bypasses RLS. A missing tenant setting makes the
    comparison NULL, so no row matches (fail closed). `readable_templates` also lets every
    tenant read shared rows whose tenant_id is NULL (platform role templates), never write them.
    """
    using = f"{column} = {_CURRENT_TENANT}"
    if readable_templates:
        using = f"({using} OR {column} IS NULL)"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({using}) WITH CHECK ({column} = {_CURRENT_TENANT})"
    )


def make_append_only(table: str) -> None:
    """Reject UPDATE, DELETE and TRUNCATE for every role, including the owner. Grants already
    withhold them from the app role; the trigger also stops a mistaken migration or script."""
    op.execute(
        "CREATE OR REPLACE FUNCTION reject_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME "
        "USING ERRCODE = 'insufficient_privilege'; END $$"
    )
    op.execute(
        f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION reject_change()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_change()"
    )
