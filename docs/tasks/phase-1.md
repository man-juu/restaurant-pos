# Phase 1 task list (back-office core)

Status as of 2026-10-07. Order follows docs/08 section 3. PR #1 stays open (not merged) until the owner says so.

## Done

- [x] 1a Tenant settings: tax, service charge, payment methods, numbering, approval and alert rules (FR-TEN-004 to 009)
- [x] 1b part 1 Catalog backend: units, categories, items, translations, conversions (FR-CAT-001, 002, 008, 009)
- [x] Legacy app reviewed, ideas kept (docs/existing-code-review.md), old branches deleted
- [x] Complexity limits in lint: ruff C90 (max 10), PLR09xx, SIM/PERF; ESLint complexity 10, max-depth 3, max-params 4

## Remaining in Phase 1

| # | Slice | Requirements | Notes |
| --- | --- | --- | --- |
| 1 | 1b part 2: channels and channel list prices with start dates | FR-CAT-004 | modifiers (FR-CAT-003) and per-outlet overrides (FR-TEN-011) moved to Phase 2 (docs/09 0.20) |
| 2 | 1b part 3: upload engine (menu/ingredient photos, login background), optional by default | FR-CAT-001 photo, theme background | file type sniffing, size limit, re-encode images, no SVG |
| 3 | 1b part 4: free AI images with usage counter, block at 85% of free limit plus per-tenant daily cap | FR-CAT-013, ADR-022 | off until platform configures the key |
| 4 | 1b part 5: catalog screens (list, search, edit form, units, categories) EN/ID, phone/tablet/desktop | FR-CAT-001 to 004 | ux-review checklist |
| 5 | 1c BOM versions, nesting with cycle check, theoretical cost and margin, food-cost alert | FR-CAT-005 to 007, 012 | cost hidden without catalog.cost.view |
| 6 | 1d Import/export CSV/XLSX, demo seed (fictional menu shaped like the legacy one) | FR-IMP-001 to 003 | XLSX library needs owner approval |
| 7 | 1e Inventory ledger, batches, FEFO, moving average, balances, reversals | FR-INV-001 to 006, 014, FR-X-005 | append-only, same-transaction postings |
| 8 | 1f Purchasing: vendors, PR, PO, receiving, quick purchase, PDF, invoice attachment | FR-PUR-001 to 006, 010, 011 | attachment optional, configurable mandatory |
| 9 | 1g Production with yield and costing, shelf-life labels, prep list | FR-PRD-001 to 004, 007, 008 | |
| 10 | 1h Transfers with approval, delivery note, discrepancies | FR-TRF-001 to 004 | |
| 11 | 1i Counts, waste, adjustments with approvals | FR-INV-007 to 009 | |
| 12 | 1j Stock levels, DOI, alerts, reorder suggestions, producible quantity, notification center | FR-INV-010 to 013, 020, FR-NTF-001 to 003 | |
| 13 | 1k Manual daily sales entry, recipe consumption, day lock, platform item mapping | FR-SAL-001 to 003, FR-CAT-010 | |
| 14 | 1l Reports and variance | FR-RPT-001 to 006, 010, 011, FR-INV-015 | |
| 15 | 1m Admin usage, feature flags, audit filters/export, subscription notices | FR-ADM-004, 006, FR-AUD-004, FR-SUB-006 | |
| 16 | 1n Load test (k6), full security review, pilot | Gate 1 | |

## Cross-cutting follow-ups

- Permission backfill: new module permissions reach only tenants created after the release. Add a migration-safe "sync role templates" admin command before the first real tenant (before 1n).
- Local dev database: document the non-Docker setup (roles, grants) in the README, or always use `docker compose`.
- Pin base images and GitHub Actions by digest; Dependabot (from docs/security-practices.md open items).
- Dedicated backup database role instead of the owner role.
- [x] Cognitive complexity (complexipy, eslint-plugin-sonarjs) and file-size limits added with owner approval.
- Settings screen in the screen previews artifact.

## Code-quality rules applied to every slice

- One responsibility per function; services hold business rules, routers only map HTTP to services.
- Cyclomatic complexity at most 10 per function; nesting at most 3; prefer early returns and lookup tables over long if/else chains.
- Queries: no N+1 (query-count guards in tests/test_performance.py), keyset pagination, indexes lead with tenant_id, whitelisted sort columns.
- Security: deny by default, RLS on every tenant table, look up referenced rows under RLS before writing (foreign keys ignore RLS), escape LIKE patterns, strict schemas (`extra="forbid"`), no secrets in logs.
