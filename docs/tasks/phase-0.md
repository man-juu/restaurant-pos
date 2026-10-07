# Task Brief: Start and Phase 0 (Foundation)

Read `CLAUDE.md` first. Specs are in `docs/`. This brief is the work order for Claude Code.

## Starter prompt (paste into Claude Code from the repo root)

> Read CLAUDE.md and docs/tasks/phase-0.md. Do Step 0 only: review the existing code read-only and write docs/existing-code-review.md. Do not change any code. Then summarize the gaps in under 15 lines and ask me the questions you need answered.

## Step 0. Orientation (read-only)

1. List the repository structure, languages, frameworks, dependencies, database schema or models, tests, and how it is run.
2. Compare with `docs/04` (architecture) and `docs/05` (data model).
3. Write `docs/existing-code-review.md` with: what exists, quality assessment, what to keep, what to rewrite, risks (secrets in history, missing tenant isolation, floats for money, and so on).
4. Do not modify, move or delete anything. Do not run anything that touches real data.
5. Ask the owner which parts to keep.

Stop after Step 0 until the owner replies.

## Step 1. Approval gate

Confirm with the owner that every document in the `docs/README.md` approval table is **Approved**, and that open questions in `docs/09` are answered or their defaults accepted. Record the result in the changelog of `docs/09`. Do not start Step 2 before this.

## Step 2. Phase 0 slices

Do one slice at a time on its own branch. For each: restate requirement IDs and acceptance criteria, propose the plan in a few lines, wait for a go-ahead on the first slice, implement with tests, run the full checks, update docs, summarize in under 15 lines.

### 0.1 Repository and tooling

Deliverables: monorepo layout from `CLAUDE.md`, Docker Compose for local development (database, API, frontend dev server), pre-commit (ruff, Prettier, secret scan), CI workflow (lint, types, tests), `.env.example`, ADR template in `docs/adr/`, `docs/data-inventory.md` stub.

Accept when: `docker compose up` starts the stack from a clean clone; CI is green on an empty change; no secret is tracked by Git.

### 0.2 Backend skeleton

Requirements: FR-X-003, FR-X-004, NFR-010, NFR-011.

Deliverables: settings via environment, structured JSON logging with request IDs, one error format (`code`, `message`, `details`, `request_id`), `/health`, module registry that loads `module.py` manifests, import-linter contracts from `docs/04`, idempotency-key dependency, cursor pagination and filter helpers.

Accept when: a deliberate cross-module import fails CI; `/health` reports database status; error format covered by tests.

### 0.3 Database baseline and tenancy

Requirements: FR-TEN-001, FR-TEN-002; `docs/05` sections 1, 2.1, 4.

Deliverables: Alembic setup, database roles (owner, app, readonly), helper that enables and forces RLS on a table, a database session helper that sets `app.tenant_id` per transaction with `set_config(..., true)`, tables `tenants`, `outlets`, `users`, `memberships`, `roles`, `role_permissions`, `membership_outlets`, `audit_log` (append-only, UPDATE and DELETE revoked), UUIDv7 generation.

Accept when: a schema test fails if any table with `tenant_id` lacks RLS or FORCE; with tenant A's context, tenant B's rows are invisible and inserting a row for tenant B is rejected; with no context, zero rows are returned; migration upgrade from empty database passes.

### 0.4 Authentication

Requirements: FR-IDN-001 to 003, 005 to 009; FR-AUD-001 to 003; `docs/06` section 3.

Deliverables: email and password sign-in (Argon2id), server-side sessions in `__Host-` httpOnly cookies, CSRF token, logout and session list and revoke, TOTP enrolment and verification with recovery codes, invitations, password reset, lockout and rate limiting, audit events for each security action.

Accept when: tests cover lockout, expired and reused invitation and reset tokens, session revocation taking effect on the next request, CSRF rejection, and TOTP required for owner and co-owner roles.

### 0.5 Authorization framework

Requirements: FR-IDN-010, FR-TEN-003, FR-SUB-004; `docs/03`.

Deliverables: permission registry (`module.resource.action`) with default role templates, a request dependency that evaluates session, tenant membership, subscription state, module enabled, permission and outlet scope in the documented order, "cannot approve own request" rule, approval service skeleton, `/me/capabilities` endpoint.

Accept when: a test lists all routes and fails for any without declared permissions; generated tests show a role without permission receives 403 and another tenant's object receives 404; read-only subscription blocks every write route; disabled module returns 403 with a clear code.

### 0.6 Platform admin

Requirements: FR-ADM-001 to 003, FR-SUB-001 to 003, 005.

Deliverables: separate admin user store and sessions with mandatory TOTP, tenant create, edit, suspend and delete, profile and module assignment, subscription fields (plan type, start, end, grace days, reminders on or off), read-only impersonation requiring a reason with automatic expiry, all logged and visible to the tenant owner, minimal admin UI.

Accept when: admin actions appear in the tenant's audit log; impersonation cannot write; expired impersonation is rejected; subscription transitions (active, expiring, grace, read-only) are produced by a daily job and tested with a controllable clock.

### 0.7 Frontend shell

Requirements: FR-X-001, FR-X-002, FR-X-006, FR-SUB-002.

Deliverables: Vite React TypeScript app, routing, desktop, tablet and phone layouts, i18n with EN and ID, locale formatting for money, dates and numbers, capability-driven navigation, generated API client wired into CI, login and TOTP screens, tenant switcher, subscription banner, PWA manifest and install.

Accept when: no hard-coded user strings (lint rule or test); client regeneration produces no diff in CI; Playwright covers sign-in, language switch, and module-hidden navigation; layouts verified at phone, tablet and desktop widths.

### 0.8 Deployment and operations

Requirements: NFR-003 to NFR-005; `docs/07`.

Deliverables: production Dockerfiles (non-root), production and staging Compose files, Caddyfile with security headers and rate limits, GitHub Actions pipeline (build, push image, deploy to staging, manual approval, deploy to production, health check and rollback), backup script (encrypted dump to off-site storage) and restore script, monitoring checklist, runbooks in `docs/runbooks/` (deploy, rollback, restore, rotate secrets, incident).

Accept when: a deploy to staging runs from the pipeline; a restore drill into a scratch database succeeds and passes a basic integrity check; rollback to the previous image is demonstrated.

Items needing the owner (do not attempt alone): provisioning the VPS, DNS and domain, Cloudflare setup, choosing the backup storage provider, creating accounts or paying for anything.

## Gate 0 checklist

- [ ] CI green; staging deploy by pipeline.
- [ ] Two test tenants cannot see each other's data (automated).
- [ ] Admin can create a tenant and set its subscription.
- [ ] Backup and restore drill passed.
- [ ] `docs/README.md` statuses and `docs/09` changelog updated.

## Stop and ask

Stop and ask the owner before: deviating from an ADR; adding a dependency not listed in `CLAUDE.md`; changing the data model beyond `docs/05`; touching production, DNS, credentials or paid services; destructive Git or database operations; or when a requirement is ambiguous.
