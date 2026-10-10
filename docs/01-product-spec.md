# 01. Product Specification

## 1. Purpose

Build one platform that lets food businesses run sales, stock, purchasing, production, tables and basic accounting from any device, with each business (tenant) seeing only its own data and switching on only the modules it needs.

## 2. Problem

Small and mid-size Indonesian F&B operators typically juggle a POS app, delivery-platform tablets, spreadsheets for stock, and a separate accountant. The result: no true food cost (HPP) per menu item, stock that expires or runs out unexpectedly, no reconciliation between what recipes say was used and what was actually used, and slow month-end closing.

The first real user is a cloud kitchen with a central kitchen and about 5 to 7 outlets that supplies branches with frozen ingredients and buys other items from outside vendors.

## 3. Tenant profiles

A profile is a starting configuration (modules on/off, defaults), not a separate code path. Any tenant can change its modules later.

| Profile | Typical business | Modules on by default |
| --- | --- | --- |
| Restaurant | Dine-in with tables, some takeaway and delivery | POS, tables, reservations, kitchen display, inventory, purchasing, finance |
| Cloud kitchen | Delivery-platform orders only (GrabFood, GoFood, ShopeeFood); no service charge | Sales entry, inventory, purchasing, production, finance |
| Central kitchen group | One production site supplying branches | Inventory, production, transfers, purchasing, finance |
| Hybrid | Any mix of the above across outlets | Chosen per tenant; outlet type decides what each outlet sees |

## 4. Users

| Actor | Scope | Summary (detail in 03) |
| --- | --- | --- |
| Platform administrator | Whole platform | Creates and supports tenants, sets plans, modules and subscription dates. Never sees tenant data without an audited reason. |
| Owner | One tenant | Full control, billing contact, can delete the tenant and transfer ownership. |
| Co-owner | One tenant | Full operational control except ownership and deletion. |
| Staff | Chosen outlets | Role-based access: manager, cashier, waiter, kitchen, warehouse, purchaser, accountant, or custom roles. |

## 5. Goals

1. Accurate stock and HPP: every sale consumes ingredients through recipes; every purchase, production, transfer, waste and count is a permanent ledger entry.
2. One shared core serving restaurants and cloud kitchens, with modules switched per tenant.
3. Usable on desktop, tablet and phone from one installable web app (PWA).
4. Tenant isolation strong enough to survive a coding mistake (database-enforced).
5. Low running cost: a single small VPS at the start, with a clear path to scale.
6. Indonesian-first (IDR, local taxes, EN/ID languages, local payment methods) while staying country-neutral in design.
7. Maintainable by one developer.

## 6. Non-goals (this version)

- Payroll, attendance and shift scheduling (labor cost is entered as a figure, not computed).
- Direct integrations with GrabFood, GoFood or ShopeeFood APIs (manual entry first; integration through an approved partner later).
- Native iOS/Android apps (the PWA covers them).
- Full statutory tax filing (we produce reports; the accountant files).
- Customer-facing ordering app or public reservation site (Phase 4 at earliest).
- Automatic price scraping of marketplaces.

## 7. Product principles

1. **Ledger first.** Stock and money are append-only entries. Balances are derived. Corrections are reversals, never edits.
2. **Configurable, never forked.** Differences between tenants are settings and modules, not branches of code.
3. **Server decides.** Permissions, modules, subscription state and tenant scoping are enforced on the server and in the database. The UI only reflects them.
4. **Online-first, offline-ready.** Version 1 needs internet. Code keeps writes idempotent so offline mode can be added later.
5. **Boring technology.** Proven tools, few moving parts, everything runs from one `docker compose`.
6. **Explainable numbers.** Every cost, stock and report figure can be traced to the entries behind it.

## 8. Release scope

| Phase | Theme | Outcome for the user |
| --- | --- | --- |
| 0 | Foundation | Tenants, users, roles, outlets, module switches, audit log, admin console, deploy pipeline |
| 1 | Back-office core | Items and recipes, stock ledger, purchasing, production, transfers, counts, manual daily sales entry, alerts, core reports |
| 2 | Front of house and money | Cashier POS, tables, kitchen display, shifts, receipts, finance-lite (cash, expenses, P&L) |
| 3 | Depth | Reservations, full double-entry accounting, EOQ and forecasting, notifications, menu engineering |
| 4 | Reach | Offline mode, payment gateway, platform integration via partner, loyalty, public booking |

Details and exit criteria are in [08](08-roadmap-engineering.md).

## 9. Success measures (targets to validate with the first tenant)

| Measure | Target |
| --- | --- |
| Time for an outlet to record a day's platform sales manually | Under 5 minutes |
| Cashier time to take and pay a typical 3-item order | Under 30 seconds |
| Stock count variance visible per ingredient after each count | 100% of counted items |
| HPP per menu item available for every priced item | 100% of items with a recipe |
| Cross-tenant data exposure in automated tests | 0 |
| Monthly infrastructure cost at launch | Under Rp 250.000 including tax (verify) |

## 10. Constraints and assumptions

- One developer; work is sliced into small finished releases.
- No credit card: paid services must accept virtual account, e-wallet, QRIS or bank transfer.
- Hosting in Indonesia preferred for latency and data-protection posture.
- Tax rates and charge rules are configuration, never hard-coded, because local rates vary by region.
- Free AI APIs may use submitted data for training, so AI is optional and never receives tenant or customer data.

## 11. Glossary

| Term | Meaning |
| --- | --- |
| Tenant | One customer business using the platform. The UI calls it "Business". |
| Outlet | A physical location: restaurant, branch, cloud-kitchen site or central kitchen. |
| Item | Anything stocked or sold: raw ingredient, semi-finished good, or menu item. |
| BOM / recipe | The list of ingredients and quantities that make one unit of an item. |
| HPP | Harga pokok penjualan: cost of goods sold. |
| Batch / lot | A received or produced quantity with its own expiry date. |
| FEFO | First expired, first out: usage consumes the earliest-expiring batch first. |
| Stock opname | A physical stock count compared with system quantity. |
| DOI | Days of inventory: stock on hand divided by average daily usage. |
| PBJT | Pajak Barang dan Jasa Tertentu: regional tax on food and beverage sales (formerly restaurant tax, PB1). |
| KOT / KDS | Kitchen order ticket / kitchen display system. |
| Channel | Where an order came from: dine-in, takeaway, a delivery platform, wholesale. |
| Business date | The accounting day of a sale, which may differ from the calendar day for late-night outlets. |
