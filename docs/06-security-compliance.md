# 06. Security and Compliance

Goal: defense in depth, so that one mistake does not become a breach. No system is unhackable; we aim to be hard to attack, easy to audit and quick to recover. Review checklist: OWASP ASVS Level 2.

## 1. Assets and trust boundaries

| Asset | Why it matters |
| --- | --- |
| Tenant business data (sales, costs, recipes, vendors) | Competitive and financial value to each tenant |
| Staff and customer personal data | Legal duty under Indonesia's personal data protection law |
| Credentials and sessions | Gateway to everything |
| Ledgers and audit log | Integrity of money and stock |
| Backups | A second copy of everything |

Boundaries: internet to Cloudflare, Cloudflare to the server, app to database, tenant to tenant, tenant to platform admin.

## 2. Threat model (STRIDE summary)

| Threat | Example | Primary defenses |
| --- | --- | --- |
| Spoofing | Stolen password, session theft | Argon2id, two-factor for privileged roles, httpOnly Secure SameSite cookies, session revocation, login rate limits |
| Tampering | Edit a past sale or stock entry | Append-only ledgers, revoked UPDATE/DELETE, reversal workflow, audit log |
| Repudiation | "I never voided that" | Audit log with user, device, time, request ID |
| Information disclosure | Tenant A reads tenant B | RLS with FORCE, composite FKs, cross-tenant tests, per-field cost hiding, no tenant ID from client |
| Denial of service | Request floods | Cloudflare, Caddy and app rate limits, request size limits, query timeouts |
| Elevation of privilege | Cashier calls an admin endpoint | Server-side permission and scope checks on every route, deny by default, tests per endpoint |
| Insider fraud | Fake voids, inflated waste | Approval rules, discount limits, variance reports, shift cash reconciliation |
| Supply chain | Malicious dependency | Lock files, Dependabot, pip-audit, npm audit, minimal base images, image scanning |
| Platform admin abuse | Support reads tenant data | Impersonation read-only, reason required, time-limited, logged, visible to the tenant owner |

## 3. Authentication

| Control | Detail |
| --- | --- |
| Password storage | Argon2id with tuned parameters; no maximum length below 128; breached-password check (offline hash list) |
| Password policy | Minimum length 12 for owners, co-owners and admins; 10 for staff; no composition rules, no forced periodic rotation |
| Two-factor | TOTP required for owner, co-owner, platform admin; recovery codes stored hashed |
| Lockout | Exponential delay after repeated failures per account and per IP |
| Sessions | Random 256-bit IDs stored hashed server-side; idle and absolute timeouts; rotation on privilege change; revocation list is the table itself |
| Cookies | `HttpOnly; Secure; SameSite=Lax`; `__Host-` prefix |
| CSRF | Per-session token required on state-changing requests |
| POS PIN | Only on registered devices; hashed; lockout; reset by a manager |
| Invitations and resets | Single-use random tokens, stored hashed, short expiry |

## 4. Authorization

1. Deny by default: an endpoint without declared permissions is rejected by a router-level check and caught by a test that lists all routes.
2. Order of checks in 03 section 1.
3. Object-level checks: every lookup by ID is scoped by tenant and outlet; there is no "get by ID" without scope.
4. Sensitive fields (cost, margin, vendor bank details) are removed server-side for roles without permission.
5. Mass-assignment protection: request schemas list allowed fields explicitly.

## 5. Tenant isolation

Defense layers, any one of which should stop a leak:

1. Application: tenant resolved from the session; repositories require a tenant context.
2. Database: RLS with FORCE; restricted application role; fail closed when the setting is absent.
3. Schema: composite foreign keys including `tenant_id`.
4. Tests: a generated suite hits every route with tenant B credentials against tenant A object IDs and expects 404; a schema test asserts RLS on every tenant table.
5. Operations: backups and exports are per tenant filtered; admin impersonation is audited.

## 6. Input, output and API hardening

- Pydantic validation on every input; reject unknown fields; size limits.
- ORM with parameterized queries only; raw SQL is reviewed and tested.
- Output encoding by React; no `dangerouslySetInnerHTML`; user-supplied HTML is never rendered.
- Strict Content Security Policy, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS.
- CORS closed by default; the PWA and API share one origin.
- File uploads (photos, attachments): type allow-list, size limit, content sniffing, re-encode images, random names, served from a separate path with `Content-Disposition` and no execution.
- Rate limits: per IP at Caddy and per user and tenant in the app (stricter on login and reset).
- Idempotency keys prevent duplicate postings on retries.
- Safe PDF and spreadsheet generation: escape cells that start with `=`, `+`, `-`, `@` to prevent formula injection.
- No server-side fetch of user-supplied URLs.

## 7. Secrets and configuration

- Secrets only in environment variables or a server-side file with mode 600, never in Git. A pre-commit and CI secret scan runs on every change.
- Separate secrets per environment; rotation procedure documented.
- Sensitive columns (TOTP secrets, vendor bank details) encrypted at the application level with a key held outside the database.
- Database roles: owner (migrations), app (read/write, no DDL, no superuser), readonly (reports, optional), backup.

## 8. Infrastructure hardening (see 07)

SSH keys only, no root login, fail2ban or equivalent, firewall allowing only 80 and 443 plus SSH from known addresses, automatic security updates, Docker containers running as non-root with read-only file systems where possible, no database port exposed publicly, Cloudflare in front with the origin allowing only Cloudflare addresses.

## 9. Logging, monitoring and audit

- Structured JSON logs with request ID, tenant ID, user ID; no passwords, tokens, full card or bank numbers, or customer phone numbers in logs.
- Security events (failed logins, lockouts, permission denials, role changes, impersonation) are written to the audit log and alert on thresholds.
- Error tracking with PII scrubbing.
- Uptime checks and alert routing to the owner by email and an additional channel.

## 10. Backup and recovery security

- Encrypted before leaving the server; keys stored separately from backups.
- Backups are write-only from the server; deletion requires a separate credential.
- Restore is rehearsed monthly into a scratch database and verified with the ledger invariants.

## 11. Compliance: Indonesian personal data protection (UU PDP) **(verify with counsel)**

| Topic | Approach |
| --- | --- |
| Roles | The tenant is the data controller for its staff and customers; the platform is the processor. A data processing agreement is part of the terms. |
| Data minimization | Customer data limited to name and phone with a consent timestamp; staff data limited to name, email, role. |
| Data inventory | Maintained in this repo (`docs/data-inventory.md`, created in Phase 0). |
| Subject rights | Export and deletion or anonymization on request through the owner or admin. |
| Breach handling | Incident response plan below; the law requires written notification within a short deadline (3 x 24 hours as understood, **verify**). |
| Hosting location | Indonesian data center preferred. |
| Consent | Stored with timestamp and purpose; reservations and loyalty only. |

Other items to confirm with an accountant or tax advisor before launch: tax rates and calculation order for regional food-and-beverage tax and service charge, whether tenants are VAT-registered businesses, invoice and receipt format requirements, and bookkeeping retention periods.

## 12. Incident response (outline)

1. Detect (alerts, report) and open an incident record.
2. Contain: revoke sessions, rotate secrets, isolate the server if needed.
3. Assess scope using logs and the audit log; identify affected tenants.
4. Notify affected tenants and, where required, the authority.
5. Recover from clean backups or images.
6. Review within a week; fix root cause; add a test.

## 13. Security testing plan

| Activity | When |
| --- | --- |
| Static analysis (ruff security rules, Bandit, ESLint security plugin) | Every change |
| Dependency audit (pip-audit, npm audit, Dependabot) | Every change and weekly |
| Secret scanning | Every change |
| Container image scan | Every build |
| Automated tenant-isolation suite | Every change |
| OWASP ZAP baseline scan against staging | Every release |
| Manual review against ASVS L2 checklist | End of each phase |
| Independent penetration test | Before the first external paying tenant, and yearly |
| Restore drill | Monthly |
