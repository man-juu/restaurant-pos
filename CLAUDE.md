# CLAUDE.md: Restaurant POS / ERP

Multi-tenant, modular POS and back-office ERP for restaurants, cloud kitchens and central-kitchen groups. Indonesia first (IDR, EN/ID), country-neutral design. Built and maintained by one developer.

## Source of truth

All specs live in `docs/`. Read the relevant document before working on a slice; do not guess.

| Need | Read |
| --- | --- |
| What and why | `docs/01-product-spec.md` |
| Exact requirements (IDs like `FR-INV-014`) | `docs/02-functional-spec.md` |
| Roles and permissions | `docs/03-roles-permissions.md` |
| Structure, module rules, tenancy | `docs/04-architecture.md` |
| Tables, ledger rules, rounding | `docs/05-data-model.md` |
| Security checklist | `docs/06-security-compliance.md` |
| Hosting, deploy, backups | `docs/07-infrastructure-cost.md` |
| Build order, testing, definition of done | `docs/08-roadmap-engineering.md` |
| Decisions (ADRs) and open questions | `docs/09-decisions-open-questions.md` |
| Current task brief | `docs/tasks/phase-0.md` |

If code and docs disagree, the docs win until the owner agrees to change them. Changes to a decision go through a new ADR in `docs/09`; never silently deviate.

## Status gate (read first)

Check the approval table in `docs/README.md`. If any document is still **Draft**, do **not** write application code. Do only read-only work (repo review, gap report, doc improvement suggestions) and ask the owner to approve. Existing prototype code, if present, is unreviewed (Q-001): inspect it first, report keep/rewrite recommendations in `docs/existing-code-review.md`, and change nothing until the owner decides.

## Stack (decided)

- Backend: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL, argon2-cffi, cryptography, authlib (Sign in with Google, ADR 0.57), pywebpush (web push, ADR 0.72). Jobs: Postgres-backed queue (no Redis at launch, ADR-005).
- Frontend: React + TypeScript + Vite, React Router, Tailwind + Radix/shadcn-style components, TanStack Query, React Hook Form + Zod, i18next, PWA. API client generated from OpenAPI.
- Run: Docker Compose; Caddy serves the built PWA and proxies the API. One small VPS, Cloudflare in front.
- Quality: ruff, mypy, import-linter, pytest (+ Hypothesis), ESLint, `tsc`, Vitest, Playwright, k6.

## Layout

```
backend/   app/core, app/modules/<module>, app/admin, migrations, tests
frontend/  src/app, src/features, src/components, src/lib, src/locales
infra/     compose files, Caddyfile, deploy and backup scripts
docs/      specs, ADRs, runbooks, task briefs
```

Each backend module has `models.py, schemas.py, service.py, router.py, events.py, permissions.py, module.py`. Other modules use a module only through its `interface.py`; cross-module reactions go through in-transaction events (`app/core/events.py`).

## Commands

Run from the repository root unless noted.

```
docker compose up --build           # local stack: db :5432, migrate (one-shot), api :8000, admin :8001, web :5173
docker compose down -v              # reset the local database (destroys local data only)
pre-commit install                  # once: ruff, Prettier, gitleaks on every commit

# backend/ (first: python -m venv .venv && .venv/bin/pip install -e ".[dev]")
ruff check . && ruff format --check .
mypy
lint-imports                        # layer contract (per-module rules: tests/test_module_registry.py)
complexipy app scripts --max-complexity-allowed 15   # cognitive complexity
pytest                              # needs PostgreSQL: docker compose up -d db (creates pos_test)
alembic revision --autogenerate -m "..."  # then review by hand; add RLS via migrations/helpers.py
alembic upgrade head                # uses MIGRATION_DATABASE_URL (owner role)
python -m app.admin.cli create-admin you@example.com "Name" super_admin   # first platform admin
python -m app.admin.cli subscription-job                                  # daily job (worker container runs it)
python -m app.admin.cli alerts-job                                        # stock alerts (worker runs it every 10 minutes)
python -m app.admin.cli invariants-job                                    # nightly ledger checks I-1 to I-4 (worker runs it)
python -m app.admin.cli sync-roles                                        # new module permissions for existing tenants (prod migrate runs it)
python -m app.admin.cli vapid-keys                                        # once: key pair for web push (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY)

# frontend/ (first: npm ci)
npm run dev | lint | typecheck | test | build | format:check | audit:deps
npm run e2e                         # Playwright, phone/tablet/desktop, API mocked
npm run api:generate                # after backend: python -m app.openapi ../frontend/src/lib/api
# adding a package: npm install --before=<7 days ago> <pkg>   (cooling-off; scripts are off via .npmrc)
```

Without a local Python 3.12 or browsers (for example on Windows), run the same checks in containers (the stack must be up):

```
docker compose run --rm --no-deps -v "$PWD/backend:/app" migrate sh -c 'OWNER_DATABASE_URL=$MIGRATION_DATABASE_URL pytest -q'
docker run --rm --ipc=host -v "$PWD/frontend:/app" -v pw-node-modules:/app/node_modules -w /app mcr.microsoft.com/playwright:v1.63.0-noble sh -c "npm ci && npx playwright test"
```

CI (`.github/workflows/ci.yml`) runs all of these plus a gitleaks scan and production image builds.
Release: tag `vX.Y.Z` on `main` → `release.yml` (images, staging, ZAP); production: run `deploy-prod.yml` by hand. Runbooks: `docs/runbooks/`.

Database roles: migrations run as the owner; the API connects as `pos_app` (no superuser, no table ownership, no BYPASSRLS); `pos_readonly` for reports; NOLOGIN `pos_auth` (BYPASSRLS) only owns the sign-in lookup functions; `pos_admin` is used only by the platform admin app (`app/admin`, port 8001) and sees tenant tables only through explicit `platform_admin` policies. New tenant tables must call `enable_tenant_rls` and `grant` from `migrations/helpers.py`; `tests/test_schema_security.py` fails otherwise.

Every route needs `Depends(require("module.resource.action"))` (or `public()` for sign-in style routes); include routers with `app.core.access.policy.include`. The app refuses to start otherwise. Module permissions and default role grants go in the module's `ModuleManifest`.

## Non-negotiable rules

1. **Tenant isolation.** Every tenant table has `tenant_id`, RLS enabled and FORCED, and a leading `tenant_id` index. Set the tenant per transaction with `set_config('app.tenant_id', :id, true)`; never session-level. The app role is not a superuser or table owner. A test must fail if any tenant table lacks the policy.
2. **Server decides.** Permission, outlet scope, module-enabled and subscription state are enforced on the server for every route (deny by default). UI hiding is cosmetic. Never take the tenant ID from the client.
3. **Ledgers are append-only.** Stock movements and journals are never updated or deleted; corrections are reversals. Stock and journal postings happen in the same transaction as the business document.
4. **Module boundaries.** A module imports only `core` and declared dependencies, never touches another module's tables, and talks through service interfaces or events. import-linter must pass.
5. **Money and quantities.** Money is integer minor units (IDR scale 0). Quantities `numeric(18,4)` in base unit; unit costs `numeric(18,6)`. Never floats. Follow the rounding policy in `docs/05`.
6. **Configuration, not constants.** Tax rates, service charge, payment methods, approval thresholds and numbering are tenant settings. Never hard-code Indonesian rates. More broadly (owner, 2026-10-08): every business works differently, so rules, workflows and options are per-tenant settings or switches with sensible defaults, never one fixed behaviour.
7. **Audit.** Security-relevant and financial actions write to the append-only audit log.
8. **i18n.** No hard-coded user-facing strings; add EN and ID keys. ESLint rule `local/no-literal-text` enforces it.
9. **Idempotency.** Create endpoints that clients may retry accept an idempotency key.
10. **Secrets.** Never commit secrets, real data or `.env` files. Use `.env.example`. Do not log passwords, tokens or personal data.
11. **Migrations.** Alembic only; expand-then-contract for risky changes; test upgrade from an empty database.

## Out of scope (do not build or add)

Redis (until measured need), marketplace scraping, native mobile apps, payroll or attendance, direct GrabFood/GoFood/ShopeeFood APIs (Phase 4, partner only), AI features that receive tenant or customer data (sole exception: ADR-022, free image generation from a user-typed prompt), payment gateway (Phase 4).

## Workflow

- Work in small slices from `docs/08` and the task brief; one short-lived branch per slice; Conventional Commits.
- Before coding a slice: restate the requirement IDs, the acceptance criteria and the plan; then implement with tests.
- Every slice must meet the Definition of Done in `docs/08` section 10: tests (unit, integration with real PostgreSQL, tenant isolation, permissions), audit, EN/ID strings, security checklist, docs and ADR updates.
- Trace work to requirement IDs in commit messages and test names.
- **Every change, however small, gets a security check and a performance check before it is pushed** (owner rule):
  - Security: think through abuse of the change (injection, auth/tenant bypass, data exposure, unsafe input), run the security tests, and run `/security-review` for larger changes; record notable results in `docs/security-practices.md`.
  - Performance: backend `tests/test_performance.py` (p95 and query-count guards) and the frontend bundle budget (`npm run build` runs `scripts/check-bundle.mjs`). Never raise a budget without saying why.
- Code shape (enforced in lint and tests): cyclomatic complexity <= 10, cognitive complexity <= 15, nesting <= 3; backend files <= 400 lines (`tests/test_structure.py`), frontend files <= 250 lines and components <= 120 lines; each module keeps the standard file set. Split by responsibility rather than raising a limit.
- UI work follows `docs/ux-review.md` (Shneiderman's 8 Golden Rules, Nielsen's 10 heuristics) and its per-screen checklist.
- Update this file when commands, layout or rules change.

## Ask the owner before

The owner decides only these (2026-10-08); everything else, build and record the decision in `docs/09` (and `docs/05` for data-model changes):

- Adding a new library, plugin, tool or installation not listed above (and any outside service).
- Risky actions: anything involving production servers, DNS, accounts, paid services or credentials; destructive actions (dropping data, force-push, deleting branches or volumes); deviating from an ADR.
- Ambiguous requirements where a wrong guess is costly: ask a short question instead of guessing.

## About the owner

Solo developer who knows FastAPI and TypeScript and wants to learn best practices along the way: briefly explain the reason for non-obvious architecture or security choices. Cannot use credit cards: any paid service must accept virtual account, e-wallet, QRIS or bank transfer. The owner reads on a phone often: keep summaries short and put detail in files.
