# Open-source projects worth learning from

Researched 2026-10-07 by web search only. **Nothing was downloaded, cloned, installed or run**, so no third-party code entered this repository or this machine. Ideas are taken, not code (see licences in section 4).

## 1. Safety rules for using any repository

Viruses and ransomware in open source arrive mostly through **running** code: install scripts, build steps, binaries, and copycat repositories. Reading code is safe.

1. **Read, don't run.** Browse on github.com. If something must run, use a throwaway container with no secrets and no network.
2. **Watch for copycats.** Forks or re-uploads with the same name under an unknown account are a common malware trick. Always use the original author's repository. Example found: `markec12345678/restaurant-pos` is a copy of `ahmedali5530/restaurant-pos`. Ignore the copy.
3. **Signs of trust:** many stars and contributors over years, recent commits, real issues and replies, releases, a clear licence. **Warning signs:** a new account, few commits, binaries or `.exe`/`.zip` in the repo, obfuscated or base64 code, install scripts that download things, "AI agent" tools asking for broad permissions or keys.
4. **Dependencies:** add only packages from PyPI or npm with exact pins, and only after owner approval (CLAUDE.md). CI's gitleaks and the review step catch secrets. `pip-audit` and `npm audit` (vulnerable-package checks) are proposed for slice 0.8.
5. **Licences:** GPL and AGPL code must not be copied into this project (it would force the whole product to be open source). LGPL and MIT ideas are fine, and so is reading any code for ideas.

## 2. Projects and what to borrow

| Project | Licence | Trust | Worth learning from |
| --- | --- | --- | --- |
| [Odoo](https://github.com/odoo/odoo) (POS, Restaurant, Inventory, MRP) | LGPL-3 (community edition) | Very high: large company, huge community | Offline POS order queue and sync; floor and table UI; kitchen printer routing by category; stock routes and reordering rules; unit-of-measure categories |
| [ERPNext](https://github.com/frappe/erpnext) and [ERPNext Restaurant](https://github.com/alphabit-technology/erpnext-restaurant) | GPL-3 (ideas only) | ERPNext very high; the restaurant add-on is small | Stock ledger with posting reversal; BOM with nested sub-assemblies; batch and expiry; Indonesian-style chart of accounts templates |
| [Grocy](https://github.com/grocy/grocy) | MIT | High: long-running, active | Simple expiry tracking UX, "due soon" lists, barcode scanning flow, recipe fulfilment check ("can I cook this with stock on hand?") |
| [TastyIgniter](https://github.com/tastyigniter/TastyIgniter) | MIT | Medium to high | Reservations with table capacity, online ordering flow (Phase 4 ideas) |
| [OpenKitchen](https://github.com/clawnify/OpenKitchen) | Check before reading | **Low**: new, AI-agent oriented | Central-kitchen back-of-house scope (sub-recipe preps, supplier invoices) matches ours; read ideas only |
| [ahmedali5530/restaurant-pos](https://github.com/ahmedali5530/restaurant-pos) | Check | Medium | Modern React POS screens: order → kitchen → delivery flow |
| [Awesome-Restaurant-POS](https://github.com/ishandutta2007/Awesome-Restaurant-POS) | List | n/a | Index of more projects |

Libraries already in the plan or worth evaluating (each needs owner approval before adding):

| Library | Use | Status |
| --- | --- | --- |
| [Procrastinate](https://procrastinate.readthedocs.io) | Postgres-backed job queue | Already the candidate in `docs/04` (ADR-005) |
| [supa_audit / PostgreSQL audit trigger](https://wiki.postgresql.org/wiki/Audit_trigger) | Database-level change history | Idea: a trigger-based safety net under our app-level audit log; evaluate in slice 0.3 or later |
| fastapi-pagination, fastapi-rls | Pagination, RLS helpers | **Not needed**: we already have our own small, tested versions; fewer dependencies means less supply-chain risk |

## 3. Feature ideas from these projects

| Idea | Seen in | Fits | Effort | Suggested phase |
| --- | --- | --- | --- | --- |
| "Can I make this?" check: menu items that can't be produced with current stock are flagged in POS | Grocy, Odoo | FR-INV, FR-CAT-005 | Low | 2 |
| Prep list from par levels: kitchen sees what to prep today from stock vs target | OpenKitchen, Odoo MRP | FR-PRD-005 | Medium | 3 (could move to 2) |
| Recipe cost alert: when a vendor price change pushes a menu item's HPP above a target %, alert the owner | OpenKitchen | FR-CAT-007, FR-INV-012 | Low | 1 |
| Item-level 86 (sold out) list synced to POS and kitchen | Common in POS products | FR-CAT-003 | Low | 2 |
| Kitchen ticket routing by station with course timing (starters before mains) | Odoo, restaurant POS projects | FR-KDS-002 | Medium | 2 |
| Supplier invoice photo attached to goods receipt | OpenKitchen | FR-PUR-005 | Low | 1 |
| Shelf-life label printing with prep date and use-by | Grocy, kitchen systems | FR-PRD-006 | Low | 2 |
| Offline POS queue with idempotent sync | Odoo POS | FR-SAL-013 (our idempotency keys already prepare this) | High | 4 |

None of these change the approved scope yet. Adopting one means adding it to `docs/02` with an ID and a phase, after owner approval.
