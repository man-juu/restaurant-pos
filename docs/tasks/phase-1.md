# Phase 1 task list (back-office core)

Status as of 2026-10-07. Order follows docs/08 section 3. PR #1 stays open (not merged) until the owner says so.

## Done

- [x] 1a Tenant settings: tax, service charge, payment methods, numbering, approval and alert rules (FR-TEN-004 to 009)
- [x] 1b part 1 Catalog backend: units, categories, items, translations, conversions (FR-CAT-001, 002, 008, 009)
- [x] 1b part 2 Channels and channel list prices with start dates (FR-CAT-004)
- [x] 1b part 5 Catalog screens: items (search, type filter, edit, conversions), categories, units, channels, prices per channel; EN/ID; phone/tablet/desktop e2e (FR-CAT-001, 002, 004, 009)
- [x] 1c Recipes: versions (draft, active from a date), nesting with cycle check, expansion to ingredients, theoretical cost and margin per channel through a cost source that 1e will provide (FR-CAT-005 to 007). FR-CAT-012 (food-cost alert) is still open, see below.
- [x] 1e Inventory ledger: append-only movements, batches with expiry, FEFO, moving average per outlet, balances, reversals, valuation at any date, opening stock, negative-stock policy setting, stock screen (FR-INV-001 to 006, 014, FR-X-005). Recipe costing now uses the ledger's average costs.
- [x] 1i Waste logs (posted at once, reversible), adjustments and stock counts (full, spot, cycle, blind) with approval rules and "never your own request" (FR-INV-007 to 009). Waste photos wait for uploads (1b part 3).
- [x] Legacy app reviewed, ideas kept (docs/existing-code-review.md), old branches deleted
- [x] Complexity limits in lint: ruff C90 (max 10), PLR09xx, SIM/PERF; ESLint complexity 10, max-depth 3, max-params 4

## Remaining in Phase 1

| # | Slice | Requirements | Notes |
| --- | --- | --- | --- |
| 2 | ~~1b part 3: upload engine~~ done 2026-10-08 (item photos; background and attachments reuse it) | FR-CAT-001 photo | |
| 3 | ~~1b part 4: free AI images~~ done 2026-10-08 (off until keys are set, docs/runbooks/ai-images.md) with usage counter, block at 85% of free limit plus per-tenant daily cap | FR-CAT-013, ADR-022 | off until platform configures the key |
| 5 | 1c rest: food-cost alert (done 2026-10-09, see 0.40) | FR-CAT-012 | needs a target HPP % per item and tenant (not in docs/05: owner decision) and the notification center (1j); build with 1j |
| 6 | 1d Import/export CSV/XLSX (done 2026-10-08: items, recipes, opening stock, demo kitchen in docs/demo; vendors come with 1f), demo seed (fictional menu shaped like the legacy one) | FR-IMP-001 to 003 | XLSX library needs owner approval |
| 7 | 1e follow-ups: negative-stock and expiry alerts; nightly invariant job (I-1, I-2) | docs/05 rule 8, FR-INV-011 | with the notification center and jobs in 1j |
| 8 | 1f Purchasing (parts 1 and 2 done 2026-10-08: vendors, quick purchase, invoice photo, price history, PO with approval, receiving against PO, lead-time history, PO PDF; optional: purchase requests): vendors, PR, PO, receiving, quick purchase, PDF, invoice attachment | FR-PUR-001 to 006, 010, 011 | attachment optional, configurable mandatory |
| 9 | 1g Production with yield and costing, shelf-life labels, prep list (done 2026-10-08: production orders with yield, cost and expiry; stock levels with par; prep list; shelf-life labels) | FR-PRD-001 to 004, 007, 008 | |
| 10 | 1h Transfers with approval, delivery note, discrepancies (done 2026-10-08) | FR-TRF-001 to 004 | |
| 12 | 1j Stock levels, DOI, alerts, reorder suggestions, producible quantity, notification center (parts 1 and 2a done 2026-10-09: stock alerts, notification center, alerts job, days left, producible, reorder suggestions to draft PO, low-days alert; part 2b: approval and count-variance notifications; part 2c: food-cost alert; slice done) | FR-INV-010 to 013, 020, FR-NTF-001 to 003 | |
| 13 | 1k Manual daily sales entry, recipe consumption, day lock, platform item mapping (done 2026-10-09) | FR-SAL-001 to 003, FR-CAT-010 | |
| 14 | 1l Reports and variance (done 2026-10-09, see 0.42) | FR-RPT-001 to 006, 010, 011, FR-INV-015 | |
| 15 | 1m Admin usage, feature flags, audit filters/export, subscription notices | FR-ADM-004, 006, FR-AUD-004, FR-SUB-006 | |
| 16 | 1n Load test (k6), full security review, pilot | Gate 1 | |

## Cross-cutting follow-ups

- Permission backfill: new module permissions reach only tenants created after the release. Add a migration-safe "sync role templates" admin command before the first real tenant (before 1n).
- Local dev database: document the non-Docker setup (roles, grants) in the README, or always use `docker compose`.
- Pin base images and GitHub Actions by digest; Dependabot (from docs/security-practices.md open items).
- Dedicated backup database role instead of the owner role.
- [x] Tracking modes (exact/estimated/untracked), set on hand, standard cost (docs/09 0.31)
- [x] Cognitive complexity (complexipy, eslint-plugin-sonarjs) and file-size limits added with owner approval.
- Settings screen in the screen previews artifact.

## Code-quality rules applied to every slice

- One responsibility per function; services hold business rules, routers only map HTTP to services.
- Cyclomatic complexity at most 10 per function; nesting at most 3; prefer early returns and lookup tables over long if/else chains.
- Queries: no N+1 (query-count guards in tests/test_performance.py), keyset pagination, indexes lead with tenant_id, whitelisted sort columns.
- Security: deny by default, RLS on every tenant table, look up referenced rows under RLS before writing (foreign keys ignore RLS), escape LIKE patterns, strict schemas (`extra="forbid"`), no secrets in logs.
