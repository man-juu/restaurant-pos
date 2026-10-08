# Security practices and review log

Companion to `docs/06-security-compliance.md`. Its job: map common real-world attacks to the controls in this project, record what is done and what is planned, and define how we test (including penetration tests). Review it at every phase gate.

References (all free): [OWASP ASVS 5.0](https://owasp.org/projects/asvs) (our checklist, Level 2, NFR-009), [OWASP Top 10:2025](https://owasp.org/Top10/2025/), [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/), [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html) (passwords and MFA), PostgreSQL docs on [row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) and [SECURITY DEFINER](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY), CIS Benchmarks for Ubuntu and Docker (server hardening, slice 0.8). Suggested reading: *Web Application Security* by Andrew Hoffman (O'Reilly), *Alice and Bob Learn Application Security* by Tanya Janca, and *The Web Application Hacker's Handbook* (older but still the classic for testing).

## 1. Threats and our controls

Status: ✅ done and tested, 🔜 planned (slice), 👤 owner action.

| Threat | What it looks like for us | Controls | Status |
| --- | --- | --- | --- |
| **Tenant data leak** (Top 10 A01) | One business sees another's sales or recipes | RLS forced on every tenant table, restricted DB role, per-transaction tenant, schema test fails on any unprotected table, cross-tenant tests | ✅ 0.3 |
| **Broken access inside a tenant** (A01) | Cashier approves own refund, staff sees other outlets | Permission + outlet scope on every route, app refuses to start with an unprotected route, generated 403 test over all routes, self-approval blocked, owner role protected | ✅ 0.5 |
| **Injection** (A05) | SQL injection through search or sort fields | Parameterised queries only, sort columns whitelisted, ruff security rules (`S`) in CI | ✅ 0.2 |
| **Account takeover** (A07) | Password guessing, stolen password, session theft | Argon2id, lockout per account and IP, hashed session tokens, HttpOnly Secure `__Host-` cookie, idle and absolute timeouts, instant revocation, disabled users cut off at once | ✅ 0.4a |
| | | TOTP 2FA required for owners and co-owners (code replay blocked, attempts rate-limited), recovery codes, common-password check, reset signs out everywhere | ✅ 0.4b |
| **Phishing** | Fake login page steals an owner's password | 2FA for privileged roles limits the damage of a stolen password (✅ 0.4b); in-app session list shows unknown devices (✅); email only from our verified domain with SPF, DKIM, DMARC (🔜 0.8). TOTP can still be phished in real time; passkeys (WebAuthn) are the stronger future option | ✅ partly |
| | | Train staff: only sign in at the real domain; never share codes | 👤 |
| **CSRF / clickjacking** | Another site makes your browser submit actions | SameSite=Lax cookie, per-session CSRF token, JSON-only login, `frame-ancestors 'none'` header | ✅ 0.4a (headers 🔜 0.8) |
| **XSS** | Script injected via an item name | React escapes output, no `dangerouslySetInnerHTML`, strict Content-Security-Policy, session cookie unreadable by scripts | 🔜 0.7, 0.8 |
| **Data leak through errors and logs** (A10) | Stack traces or passwords in responses or logs | One error format, never echoes input, no query strings in logs, no secrets in audit | ✅ 0.2 |
| **Ransomware / data destruction** | Server compromised and database encrypted or wiped | Nightly backups encrypted with the owner's public key, uploaded to a **different provider** with a write-only key and required bucket versioning, monthly restore drill (rehearsed 2026-10-07), append-only ledgers and audit log, rebuild runbook | ✅ 0.8 |
| **Backdoor / supply chain** (A03) | Compromised package, malicious dependency or CI action | Exact version pins (`save-exact`), owner approval for every new dependency, new versions installed only after a 7-day cooling-off (`npm install --before`), npm install scripts disabled (`ignore-scripts`), CI fails on high npm advisories and on vulnerable, yanked or removed PyPI releases (`scripts/check_dependencies.py`), gitleaks on every commit; Dependabot alerts and pinned action SHAs in 0.8 | ✅ mostly; 🔜 0.8 |
| **Server compromise** (A02) | Weak SSH, exposed database, unpatched OS | SSH keys only, provider firewall (Cloudflare IPs only on 80/443), database never published, non-root read-only containers with all capabilities dropped, automatic security updates, per-environment deploy users with forced commands | ✅ 0.8 (runbook steps 👤) |
| **Insider misuse** | Platform support reads tenant data | Separate admin app, DB role and accounts with mandatory 2FA; support role cannot change tenants; impersonation is a read-only DB transaction with reason and expiry, logged in the tenant audit log | ✅ 0.6 |
| **Secrets leak** | Password in Git or logs | `.env` ignored, gitleaks, secrets only in a root-owned server file, never logged | ✅ |
| **Repudiation** | "I never voided that" | Append-only audit log (revoked privileges + trigger) with user, time, IP, request ID | ✅ 0.3 |

## 2. Testing, including penetration tests

| Layer | Tool (free) | When | Status |
| --- | --- | --- | --- |
| Static checks | ruff `S` rules (Bandit), mypy strict, ESLint | Every commit (CI) | ✅ |
| Secret scanning | gitleaks | Every commit and full history | ✅ |
| Security unit and integration tests | pytest against real PostgreSQL | Every commit | ✅ (59 tests) |
| Dependency vulnerabilities | `pip-audit`, `npm audit`, GitHub Dependabot | CI and weekly | 🔜 0.8 (needs owner approval for `pip-audit`) |
| Dynamic scan (automated pentest) | OWASP ZAP baseline against staging | Every staging deploy | 🔜 0.8 (in `docs/07`) |
| Manual penetration test | ASVS Level 2 checklist, OWASP Web Security Testing Guide; focus on tenant isolation, auth, permissions | Before the first paying tenant, then yearly | 🔜 Phase 1 exit |
| Review per slice | `/security-review` on the branch | Each slice | ✅ (first run below) |

Never run scans against production or third-party systems without permission. Pentests run against staging with test data only.

## 3. Review log

### 2026-10-07: slices 0.1 to 0.4a

Automated security review of the whole branch. **No exploitable vulnerability found.** Hardening applied straight away:

- Disabled users now lose every session immediately (was: at session expiry). Test added.
- `REVOKE CREATE ON SCHEMA public FROM PUBLIC` made explicit, so the sign-in lookup function cannot be hijacked even on older PostgreSQL.
- Dev proxy fixed to forward `/api` paths unchanged (functional bug, not security).

Open: trusted proxy headers for real client IPs (0.8).

### 2026-10-07: dependency malware and vulnerability check (before slice 0.7)

- **Frontend, 646 npm packages** (incl. transitive): `npm audit` (GitHub Advisory Database, which includes malware advisories) found **0** issues. Only one package has an install script (`fsevents`, macOS file watching used by Vite), and install scripts are disabled anyway. All new packages were installed at versions published at least 7 days earlier.
- **Backend, 61 PyPI packages**: none has a known vulnerability, and none is yanked or removed from PyPI.
- Not possible from the build sandbox: the OSV API and npm registry signature checks (blocked by network policy). CI repeats the npm and PyPI checks on every change.

### 2026-10-07: theme, palette and performance changes

- Theme preferences from browser storage are accepted only from fixed allow-lists (mode, accent, background), so a tampered value cannot inject CSS or URLs; no HTML is built from strings.
- The single-query permission loader keeps tenant scoping in the database: every subquery runs under row-level security in the caller's tenant transaction. All cross-tenant, permission and subscription tests pass (113 backend tests).
- Session activity is written at most once a minute instead of on every request; revocation and timeouts are still checked on every request.

### 2026-10-07: slice 0.8 (deployment) review

Security review of the production images, Caddy, compose, backup and deploy pipeline. Fixed before pushing:

- **High: client IP spoofing.** uvicorn trusted proxy headers from any address, so a forged `X-Forwarded-For` could dodge the per-IP lockout and poison audit IPs. Now Caddy overwrites the header with the IP it resolved from Cloudflare, and the API trusts proxy headers only from the web container's fixed address. Verified: 4 sign-in attempts with 4 forged IPs counted against one real IP.
- **Medium: admin allow-list failed open** when unset. Now required: the stack refuses to start without it.
- **Medium: the production approval could be bypassed** with the shared deploy key or a tag on an unmerged commit. Now: one server user and key per environment with forced commands and narrowed sudo, environment-scoped secrets, releases only from commits on `main`, tag protection in the runbook.
- **Low:** strict tag validation in `deploy.sh`; S3 credentials passed to curl via stdin (not visible in the process list); `packages: write` limited to the image job; web container read-only.
- **Open (low):** base images and actions are pinned by version, not digest (Dependabot in a later slice); the backup job uses the owner role (a dedicated backup role later).

## Slice 1a review (tenant settings)

- Settings payloads use strict schemas (`extra="forbid"`, bounded rates 0..10000 bp, bounded padding); unknown keys return 422.
- Reads need `tenant.settings.view`, writes need `tenant.settings.configure`; every write, approval rule and alert rule change is audited with before/after.
- All four new tables have FORCED RLS; a test confirms one tenant cannot read another's settings.
- Database integrity errors now map to 409/422 with a generic code (no SQL text leaks); previously a bad role ID returned 500.
- Numbering uses one atomic upsert; 20 concurrent allocations gave 20 unique numbers, and a rolled-back document does not burn a number.
- Performance: the settings screen loads in 2 queries (guard: 8).

## Slice 1b part 2 review (channels and list prices, FR-CAT-004)

- Both new tables have FORCED RLS and composite (tenant_id, id) foreign keys. Foreign keys ignore RLS, so the item and channel are looked up under RLS first; a test proves tenant B cannot price A's item, use A's channel, read A's history or delete A's price (404/422, never 200).
- `outlet_id` is never taken from the client (per-outlet prices are Phase 2).
- Price input is strict: a JSON integer in minor units, 0 to 10^12; strings such as "25000" and fractions are refused (found by a test: lax mode accepted numeric strings).
- Abuse limits: price history returns at most 500 rows; the price list uses keyset pagination (max 200).
- History stays trustworthy for margin reports: only prices that have not started yet (tenant time zone) can be deleted; corrections and deletes are audited with before and after values.
- Performance: the price list of 30 items runs in a constant number of queries (guard: 8); one DISTINCT ON query served by the `(tenant_id, channel_id, item_id, valid_from)` index.
- Dev setup fixes found on a Windows checkout: `.gitattributes` keeps container scripts LF (the database init script failed with CRLF), and the dev frontend image now copies `.npmrc`, so `ignore-scripts` (supply-chain guard) also applies inside Docker.

## Slice 1b part 5 review (catalog screens)

- No new dependencies. No `dangerouslySetInnerHTML`; all names render as text, so a menu name cannot inject script.
- Edit controls are hidden without `catalog.item.update`/`create`, but the server still decides (tests in `test_catalog*.py`); the e2e test checks the read-only view.
- Forms send only writable fields: the strict API (`extra="forbid"`) would refuse extras such as `id`, and that was caught in review before shipping.
- New items carry an `Idempotency-Key`, so a retried request on a weak connection cannot create a duplicate.
- `/me/capabilities` now exposes the tenant currency and language: not sensitive, and only to members of that tenant.
- Performance: the catalog screen is a separate 6.4 KB gzip chunk loaded on demand; the entry bundle is unchanged (115.5 KB of 160 KB). The search box uses a deferred value, so typing does not send a request per key.

## Slice 1c review (recipes)

- `boms` and `bom_lines` have FORCED RLS and composite tenant foreign keys; components are looked up under RLS first, and a test proves tenant B cannot use A's ingredient, read A's recipe or see A's costing.
- Integrity: the lines of an active recipe are fixed by the service and by a database trigger (tested), so sales and production always refer to the exact recipe they used.
- Abuse limits: at most 100 lines per recipe, 10 nesting levels; the cycle walk is bounded, so a crafted recipe cannot make the server loop.
- Costs and margins are returned only with `catalog.cost.view`; cashiers see quantities only (tested).
- Every draft, change, activation and delete is audited.
- Performance: costing runs a fixed number of queries per nesting level, whatever the number of lines (test compares a 1-line and a 20-line recipe); the recipe screen adds 2 KB gzip to the lazy catalog chunk.

## Slice 1e review (inventory ledger)

- Ledger integrity: `stock_movements` has INSERT/SELECT grants only plus an append-only trigger (tested: an UPDATE by the app role fails). Corrections are reversals with `reverses_id`, unique, so a movement can be reversed once.
- Invariants checked in tests after every scenario: balances equal the sum of movements (I-1), average cost never negative (I-2).
- Concurrency: the cost row and batch balances are locked (`FOR UPDATE`) in item order, so parallel postings queue instead of double-spending a batch.
- Tenant and outlet scope: all four tables have FORCED RLS and composite tenant foreign keys; items and outlets are looked up under RLS before posting; every route checks the caller's outlet scope (tested with a storekeeper limited to one outlet, a cashier without the permission, and a second tenant using foreign ids).
- Costs and values need `catalog.cost.view`; the valuation report refuses without it.
- Opening stock carries an idempotency key, so a retried request cannot post twice.
- Performance: stock and valuation lists are keyset-paginated aggregates on `(tenant_id, outlet_id, item_id, ...)` indexes; names come in one extra query per page. The inventory screen is a 3 KB gzip lazy chunk.

## Slice 1i review (waste, adjustments, counts)

- Separation of duties: approvals refuse the document's creator (docs/03 rule 1) and anyone whose role is not named by the rule (owners excepted); tested with two managers.
- Decision endpoints accept only `approve` or `reject` (anything else is 422, never a silent reject); status checks stop double posting (`wrong_status`).
- Blind counts hide frozen system quantities from counters until submit (server-side, not only in the UI).
- All six tables have FORCED RLS and composite tenant foreign keys; outlet scope is checked on every route, including actions on an existing document (404 outside scope); tested across tenants.
- Waste carries an idempotency key; every save, submit, decision and reversal is audited.
- Performance: document lists are capped at 100 rows on a `(tenant_id, outlet_id, ...)` index; posting reuses the batched ledger engine. The migration drift test now also covers inventory tables (Alembic `env.py` imports them).

## Dev tools added (2026-10-07)

- complexipy 8.0.1 (MIT, PyPI release 2026-09-07) and eslint-plugin-sonarjs 4.2.2 (LGPL-3.0, SonarSource, dev only, not shipped in the bundle). Installed with the 7-day cooling-off; npm audit clean. Owner approved.

## Slice 1b part 3: upload engine (2026-10-08)

- Pillow 12.3.0 (released 2026-07-01, no advisories at install). Allow-list JPEG, PNG, WebP; never SVG (can carry script). `Image.verify()` before decoding; 40-megapixel limit plus Pillow's own bomb guard; 8 MB body limit enforced while streaming (413 before the whole body is read).
- Every image is re-encoded to WebP and resized to 1600 px: EXIF (GPS), ICC and any appended payload are dropped. Tested: GPS EXIF removed, SVG/PDF/GIF/truncated files rejected, a 144-megapixel PNG bomb rejected.
- Stored under a random key (`<tenant>/<uuid>.webp`), never the client file name (no path traversal). Served only to signed-in members of the owning tenant (RLS; another tenant gets 404) with `Content-Type: image/webp`, `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`.
- Uploading a photo needs `catalog.item.update`; store and link happen in one transaction; every upload and photo change is audited. Identical files are de-duplicated by SHA-256 per tenant and purpose.
- Backups now include the uploads volume, encrypted with the same public key.
- Known gap (low): if a transaction rolls back after the file is written, the file stays unreferenced on disk. Harmless (not served without a row); a sweep job can be added later.

## Slice 1b part 4: free AI images (2026-10-08)

- Only the typed prompt is sent (tested: the fake provider receives exactly the prompt). Prompt: 3 to 300 printable characters, no control characters.
- Cost can never occur: off without keys; the account must stay on the Workers Free plan (over-limit requests fail there); our own budget stops at 85% of the free allowance, counted across all tenants, plus 10 per tenant per day. The budget is reserved in a committed transaction before the call (no race on the last slot); a failed call returns the platform budget. Tested: tenant cap, platform cap across two tenants, refund on failure, disabled state.
- The returned image goes through the same Pillow checks and re-encoding as uploads. Provider errors are not echoed (could contain account details). The account id must be 32 hex characters before it is used in the URL. The API token needs only "Workers AI: Read".
- Generating needs `catalog.item.update` (cashiers get 403); every generation is audited with its prompt.

## Slice 1d part 1: item import and export (2026-10-08)

- openpyxl 3.1.5 + et-xmlfile 2.0.0 (MIT, no advisories). XLSX opened read-only with cached values only: formulas are never evaluated. Zip-bomb guard: total uncompressed size checked (50 MB) before openpyxl opens the file; 5 MB body limit while streaming; at most 2,000 rows, 40 columns, 2,000 characters per cell. CSV must be UTF-8 (BOM accepted; `;` or `,` detected).
- File names in the query are restricted to `name.csv`/`name.xlsx` without slashes (tested with `../evil.csv`); the name is only stored as a label, never used as a path.
- Export protects against CSV/formula injection: cells starting with `= + - @`, tab or CR get a leading apostrophe (tested).
- All rows are checked first; one bad row blocks the whole file, so nothing is half-imported. Same file twice is refused by SHA-256 (per tenant). Undo archives the created items (master data is never deleted). Import needs `catalog.item.create`, undo `catalog.item.update`, export `catalog.item.view` (no cost data in the export). Imports and undo are audited.
- Performance: a 2,000-row import runs about 6 queries per row in one transaction (acceptable for a one-off upload); revisit with bulk inserts if real files are larger.
- Part 2 (recipes, opening stock): same file limits and safe parsing. The check runs the real save in a savepoint that is always rolled back, so the check can never pass something the import would refuse. Opening-stock rows for outlets outside the user's scope are refused like unknown outlets (no hint that they exist); undo posts ledger reversals (never deletes) and re-checks outlet scope.

## Tracking modes and standard cost (2026-10-08)

- Standard cost is cost data: removed from item responses and exports for roles without `catalog.cost.view` (tested with a cashier), and preserved on save by such roles so a hidden value can never be wiped.
- "Set on hand" bypasses approvals only for items marked estimated; exact items get 409 `not_estimated` (tested). Needs `inventory.adjustment.create` plus outlet access; every correction is a normal audited adjustment document with ledger movements (append-only).
- A database check constraint keeps `tracking_mode` and `is_stocked` consistent.

## Slice 1f part 1: purchasing (2026-10-08)

- Vendor bank details: AES-GCM with a per-field context, never in list or save responses (only `has_bank_details`); revealed only by POST with `purchasing.vendor.manage`, audited (tested: ciphertext does not contain the account number; warehouse role gets 403).
- Quick purchase requires an idempotency key (tested: same key twice = one receipt); outlet scope enforced (out-of-scope outlet looks like 404); items, vendor and invoice upload looked up under RLS before use. Undo is a ledger reversal.
- Price history is append-only (trigger plus grants).
- Invoice photos reuse the upload engine checks; the stored file is re-encoded; the receipt can only reference an upload of purpose `invoice` in the same tenant.
- Purchase orders: every step locks the order row and checks its status (no double approve or receive); the submitter cannot approve their own order when a rule applies; receiving needs an idempotency key and cannot exceed the ordered quantity; outlet scope is enforced on list, read and PDF. The PDF escapes all user text before ReportLab markup.
- Production orders: plan needs an idempotency key; every step locks the order and checks its status; outlet scope on list, read and every step (out of scope looks like 404); cooks cannot reverse (manager only); output cannot be one of its own components; components are looked up under RLS (tested: other tenant 404, cashier 403, outlet-limited cook 404).
- Stock levels, prep list and labels: outlet scope on every call (out of scope = 404); saving levels needs `inventory.level.manage` and only accepts stocked items of the tenant (RLS lookup); label copies are capped at 50 (422 above) so a request cannot make the server render huge PDFs; PDFs are drawn as plain strings (no markup parsed) and served with nosniff.
