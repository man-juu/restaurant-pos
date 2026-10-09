# Runbook: local development without Docker

`docker compose up --build` is the normal way (CLAUDE.md). This page is for machines where Docker is not available (a cloud sandbox, a locked-down laptop). Everything below is local only; never use these passwords anywhere else.

## 1. PostgreSQL (16 or 17)

Install PostgreSQL and start it. As a superuser (`sudo -u postgres psql`):

```sql
CREATE ROLE pos_owner LOGIN SUPERUSER PASSWORD 'dev-only-password';  -- see note below
CREATE DATABASE pos OWNER pos_owner;
CREATE ROLE pos_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'dev-only-app-password';
CREATE ROLE pos_readonly LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'dev-only-readonly-password';
CREATE ROLE pos_admin LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'dev-only-admin-password';
CREATE ROLE pos_backup LOGIN NOSUPERUSER BYPASSRLS PASSWORD 'dev-only-backup-password';
GRANT pg_read_all_data TO pos_backup;
```

These are the same roles `infra/db/init/10-app-roles.sh` creates in Docker.

**Owner as superuser.** In Docker the owner is the image's superuser. The test suite creates and drops the `pos_test` database and seeds data as the owner; two tests (`test_removed_outlet_assignment_applies_immediately`, `test_fr_ten_007_adjustment_rule_needs_another_approver`) write rows under forced RLS that only a superuser owner can write. With a non-superuser owner those two fail locally and pass in CI.

## 2. Backend

```sh
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export MIGRATION_DATABASE_URL="postgresql+asyncpg://pos_owner:dev-only-password@localhost:5432/pos"
.venv/bin/alembic upgrade head
.venv/bin/pytest                      # creates pos_test, migrates it, runs everything
DATABASE_URL="postgresql+asyncpg://pos_app:dev-only-app-password@localhost:5432/pos" \
  .venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
```

## 3. Frontend

```sh
cd frontend && npm ci && npm run dev   # proxies /api to :8000
PW_CHROMIUM_PATH=/path/to/chromium npm run e2e   # if Playwright cannot download browsers
```

## 4. Load test (optional)

See `backend/tests/load/` and `docs/load-test.md`. The session cookie is `Secure`, so without TLS the scripts send it as a header; browsers need HTTPS (Caddy in Docker) to sign in.
