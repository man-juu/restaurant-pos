# 02. Functional Specification

Each requirement has an ID and a delivery phase (1 to 4, see [08](08-roadmap-engineering.md)). Phase 0 items are marked `0`. "Must" means the phase cannot ship without it.

## Module map

| Code | Module | Type | Depends on |
| --- | --- | --- | --- |
| IDN | Identity and access | Core | none |
| TEN | Tenancy and settings | Core | IDN |
| SUB | Subscription | Core | TEN |
| AUD | Audit log | Core | IDN |
| ADM | Platform admin console | Core | TEN, SUB |
| CAT | Catalog (items, units, menu, prices) | Core | TEN |
| IMP | Import and export | Core | CAT |
| INV | Inventory | Module | CAT |
| PUR | Purchasing | Module | INV |
| PRD | Production | Module | INV |
| TRF | Transfers | Module | INV |
| SAL | Sales and POS | Module | CAT |
| TBL | Tables and reservations | Module | SAL |
| KDS | Kitchen display and printing | Module | SAL |
| FIN | Finance | Module | listens to events from all |
| RPT | Reports | Module | read-only over all |
| NTF | Notifications | Module | listens to events from all |

Core modules cannot be switched off. Other modules can be switched on or off per tenant. A module cannot be enabled unless its dependencies are enabled.

---

## IDN. Identity and access

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-IDN-001 | Users sign in with email and password. Passwords are hashed with Argon2id. | 0 |
| FR-IDN-002 | Owners, co-owners and platform admins must use TOTP two-factor authentication. It is optional for other staff. | 0 |
| FR-IDN-003 | Failed sign-ins are rate limited and lock the account temporarily after repeated failures. | 0 |
| FR-IDN-004 | Staff may sign in on a registered device with a 4 to 6 digit PIN after a full sign-in on that device. PINs lock after repeated failures and can be reset by a manager. | 2 |
| FR-IDN-005 | A user can belong to several tenants and switch between them without signing in again. | 0 |
| FR-IDN-006 | Owners and co-owners invite staff by email link. Invitations expire and are single use. | 0 |
| FR-IDN-007 | Users can see and revoke their active sessions and registered devices. | 0 |
| FR-IDN-008 | Password reset by emailed one-time link; links expire and are single use. | 0 |
| FR-IDN-009 | Sessions are idle-timed out; the timeout is configurable per tenant within platform limits. | 0 |
| FR-IDN-010 | Permission checks use role-based access with outlet scope (see 03). | 0 |

## TEN. Tenancy and settings

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-TEN-001 | A tenant has legal name, display name, country, default currency, default language, default timezone and a profile (restaurant, cloud kitchen, central kitchen group, hybrid). | 0 |
| FR-TEN-002 | A tenant has one or more outlets. An outlet has a type (restaurant, branch, cloud-kitchen site, central kitchen, warehouse), address, timezone, business-day cutoff time, and active flag. | 0 |
| FR-TEN-003 | Module switches per tenant, with dependency checks and a warning before disabling a module that has data. Disabling blocks writes and hides the UI; data is kept. | 0 |
| FR-TEN-004 | Tax rules are configurable per tenant and outlet: name, rate, whether it applies to service charge, whether prices include it, and calculation order. Defaults are provided for Indonesia **(verify rates with a tax advisor)**. | 1 |
| FR-TEN-005 | Service charge is configurable (rate, on/off per channel) and applied before regional tax when so configured. It is off by default, and always off for the cloud kitchen profile. | 1 |
| FR-TEN-006 | Payment methods are configurable per tenant (cash, static QRIS, bank transfer, card terminal, e-wallet, platform settlement, voucher, house account). | 1 |
| FR-TEN-007 | Approval rules are configurable per document type and amount threshold (purchase, transfer, adjustment, void, refund, discount). | 1 |
| FR-TEN-008 | Alert rules are configurable: which alert types go to which roles or users. | 1 |
| FR-TEN-009 | Document numbering is configurable per document type, outlet and year (prefix, padding, reset policy). | 1 |
| FR-TEN-010 | Tenant data export (all data, machine-readable) can be requested by the owner. | 3 |
| FR-TEN-011 | Optional per-outlet overrides for menu availability and price; the master menu is shared by default. | 1 |

## SUB. Subscription

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-SUB-001 | Billing happens outside the app. The platform admin records a plan type (free or paid), start date and end date per tenant. Free tenants have no end date. | 0 |
| FR-SUB-002 | The reminder feature can be switched on or off per tenant. When on, owners and co-owners see a banner at configurable days before expiry asking them to transfer and message the admin. | 0 |
| FR-SUB-003 | After the end date, a configurable grace period applies, then the tenant becomes read-only: viewing and exporting are allowed; creating or changing transactions is blocked. | 0 |
| FR-SUB-004 | The server enforces read-only state on every write request. | 0 |
| FR-SUB-005 | The admin can extend, pause or suspend a tenant. Every change is audited. | 0 |
| FR-SUB-006 | Subscription state changes (expiring, grace, read-only, reactivated) notify the tenant owner in-app. | 1 |

## AUD. Audit log

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-AUD-001 | Security-relevant and financial actions are recorded: who, when, tenant, outlet, action, target, before/after summary, request source. | 0 |
| FR-AUD-002 | The audit log is append-only, cannot be edited or deleted from the application, and is viewable by owners, co-owners and users with permission. | 0 |
| FR-AUD-003 | Platform-admin actions on a tenant (including impersonation) are recorded and visible to that tenant's owner. | 0 |
| FR-AUD-004 | The log is filterable by user, action, date and target and exportable. | 1 |

## ADM. Platform admin console

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-ADM-001 | Create, edit, suspend and delete tenants; assign profile, modules and subscription. | 0 |
| FR-ADM-002 | Admin users are separate from tenant users, require two-factor authentication, and have roles (super admin, support). | 0 |
| FR-ADM-003 | Support impersonation is read-only by default, requires a stated reason, expires automatically, and is logged and shown to the tenant owner. | 0 |
| FR-ADM-004 | Usage overview per tenant: outlets, users, last activity, storage, job failures. | 1 |
| FR-ADM-005 | Platform announcements shown in-app to selected tenants. | 3 |
| FR-ADM-006 | Feature flags per tenant for staged rollouts. | 1 |
| FR-ADM-007 | Admin can trigger a tenant data export and a tenant restore request. | 3 |

## CAT. Catalog

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-CAT-001 | One item table covers three types: raw ingredient, semi-finished good, menu item. Items have SKU, name per language, category, base unit, active flag, and optional photo. | 1 |
| FR-CAT-002 | Units and conversions: each item has a base unit (g, ml, piece) and purchase/usage units that convert to it (1 kg = 1000 g; 1 box = 24 pieces). Conversions are exact. | 1 |
| FR-CAT-003 | Menu items have categories, modifiers (size, add-ons, options with price delta and optional ingredient delta), and availability flags. | 1 |
| FR-CAT-004 | Prices per channel (dine-in, takeaway, each delivery platform, wholesale), with effective dates and optional per-outlet override. | 1 |
| FR-CAT-005 | Bill of materials: a menu item or semi-finished item lists ingredient/semi-finished components with quantity, unit, and waste percentage; a semi-finished item also has a yield. BOMs may nest to any depth with cycle detection. | 1 |
| FR-CAT-006 | BOMs are versioned with effective dates; orders and productions record the BOM version used. | 1 |
| FR-CAT-007 | Each BOM shows its theoretical cost and the resulting margin per channel using current moving average costs. | 1 |
| FR-CAT-008 | Items carry shelf-life, storage type (frozen, chilled, dry), allergen tags and a stock-tracked flag. | 1 |
| FR-CAT-009 | Names and descriptions are stored per language; missing translations fall back to the tenant default language. | 1 |
| FR-CAT-010 | Menu item to delivery-platform item code mapping per platform, so imported or entered platform sales map to recipes. | 1 |
| FR-CAT-011 | Combos and bundles composed of menu items with a bundle price. | 2 |
| FR-CAT-012 | Food-cost alert: each menu item may have a target HPP % (default per tenant). When a receipt or price change raises its theoretical HPP above the target, the owner and users with permission get an in-app alert showing the cause (which ingredient, old and new price). | 1 |

## IMP. Import and export

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-IMP-001 | CSV and XLSX import for ingredients, menu items, recipes, vendors and opening stock, with a validation preview before commit and row-level error messages. | 1 |
| FR-IMP-002 | Imports are idempotent per file hash and fully reversible while no later documents depend on them. | 1 |
| FR-IMP-003 | Every list and report exports to CSV and XLSX; documents export to PDF. | 1 |
| FR-IMP-004 | Import of delivery-platform sales export files with a saved column mapping per platform. | 4 |

## INV. Inventory

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-INV-001 | Stock is tracked per tenant, outlet and item. All changes are append-only ledger movements (see 05). On-hand quantity is derived from the ledger and cached in a balance table updated in the same transaction. | 1 |
| FR-INV-002 | Movement types: purchase receipt, sale consumption, production consumption, production output, transfer out, transfer in, waste, adjustment, count correction, opening balance, vendor return. | 1 |
| FR-INV-003 | Every receipt and production output creates a batch with an optional lot code and an expiry date. Receiving a perishable item without an expiry date is blocked. | 1 |
| FR-INV-004 | Consumption selects batches by FEFO. The user can override the batch with a permission and reason. | 1 |
| FR-INV-005 | Costing uses moving average cost per item per outlet, updated on each receipt. Consumption is valued at the current average. | 1 |
| FR-INV-006 | Selling or consuming more than on hand is allowed for sales (flagged as negative stock for review) and warned for production and transfers. Policy is configurable per tenant. | 1 |
| FR-INV-007 | Stock count (opname): full, spot and cycle counts; optional blind count; counts are submitted, reviewed and then posted as correction movements with reason and approval per rules. | 1 |
| FR-INV-008 | Waste logging with reason codes (spoilage, expired, preparation loss, damaged, staff meal, other) and optional photo. | 1 |
| FR-INV-009 | Manual adjustments require a reason code and follow approval rules. | 1 |
| FR-INV-010 | Per item and outlet: minimum level, maximum level, reorder point, lead time, safety stock and preferred vendor. | 1 |
| FR-INV-011 | Days of inventory (DOI) per item and outlet from average daily usage weighted by day of week, shown on the stock screen. | 1 |
| FR-INV-012 | Alerts: below reorder point, DOI below threshold, batch near expiry, expired stock on hand, negative stock, large count variance. Delivery by in-app notification. | 1 |
| FR-INV-013 | Reorder suggestions grouped by preferred vendor, convertible into a draft purchase order. | 1 |
| FR-INV-014 | Stock valuation report per outlet and date, reproducible for any past date from the ledger. | 1 |
| FR-INV-015 | Theoretical vs actual consumption variance per item and outlet and period: theoretical from recipes and sales mix; actual from opening stock plus receipts minus closing count. | 1 |
| FR-INV-016 | Lot traceability: from a batch, list where it went (production, transfers, outlets); from a finished batch, list its source batches. | 2 |
| FR-INV-017 | Storage locations inside an outlet (walk-in freezer, dry store) with counts per location. | 3 |
| FR-INV-018 | EOQ and demand forecasting: EOQ capped by shelf life, forecast by day-of-week averages with trend, once enough history exists; suggested order quantity alongside reorder point. | 3 |
| FR-INV-019 | Barcode or QR labels for batches and scanning on receive, transfer and count. | 3 |
| FR-INV-020 | Producible quantity: for each menu and semi-finished item, how many units current stock at an outlet can make from its BOM, with the limiting ingredient. Shown on the stock screen and, from Phase 2, as a "low or unavailable" marker in the POS. | 2 |

## PUR. Purchasing

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-PUR-001 | Vendors with contact, payment terms, lead time, tax details and optional bank details. | 1 |
| FR-PUR-002 | Vendor catalog: item, vendor SKU, pack size, unit price, minimum order quantity, effective date. | 1 |
| FR-PUR-003 | Purchase request, purchase order, goods receipt, in that flow, with partial receipts and approval by amount threshold. | 1 |
| FR-PUR-004 | Quick purchase: record a market or cash purchase and receive stock in one step without a PO. | 1 |
| FR-PUR-005 | Receiving captures quantity, actual price, batch, expiry, and discrepancy against the PO. Price changes update vendor price history and moving average cost. | 1 |
| FR-PUR-006 | Vendor price and actual lead time history per item, built from real purchases and quotes. | 1 |
| FR-PUR-007 | Best-vendor suggestion per item from price, actual lead time and reliability history. No marketplace scraping. | 3 |
| FR-PUR-008 | Vendor returns and credit notes. | 2 |
| FR-PUR-009 | Vendor bills with due dates, three-way match (PO, receipt, bill) and payment recording. | 2 |
| FR-PUR-010 | PO printable as PDF and shareable as a link or file. | 1 |
| FR-PUR-011 | Supplier invoice attachment: a goods receipt or quick purchase can carry photos or a PDF of the supplier invoice or delivery note. Optional by default; a tenant setting (per outlet or document type) can make it mandatory later. | 1 |

## PRD. Production (central kitchen)

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-PRD-001 | A production order names a semi-finished item, planned quantity, outlet and date. | 1 |
| FR-PRD-002 | Starting production reserves nothing; completing it consumes components (FEFO) and creates an output batch with expiry computed from shelf-life. | 1 |
| FR-PRD-003 | Actual output quantity may differ from planned; yield variance is recorded and reported. | 1 |
| FR-PRD-004 | Output batch cost equals the cost of consumed components divided by actual output. | 1 |
| FR-PRD-005 | Production plan suggestion from open transfer requests and stock targets. | 3 |
| FR-PRD-006 | Prep sheets and production labels as PDF. | 2 |
| FR-PRD-007 | Shelf-life labels: printable labels for production output and opened or prepared items, with item name, batch, prep date and time, use-by date from shelf-life, storage type and allergens. | 2 |
| FR-PRD-008 | Daily prep list per outlet: items below their target (par) level for the day, with suggested quantities from par minus stock on hand, printable and checkable on a phone. Precursor to the planned suggestion in FR-PRD-005. | 2 |

## TRF. Transfers and delivery notes

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-TRF-001 | Flow: branch creates a request, central approves (can edit quantities), stock is picked by FEFO, shipped (stock moves to in-transit), branch receives. Rules for who may request and approve are configurable. | 1 |
| FR-TRF-002 | A delivery note is generated as PDF with batches and expiry dates. | 1 |
| FR-TRF-003 | Receiving records shortage or damage per line. Discrepancies post as adjustments with approval. | 1 |
| FR-TRF-004 | Transfers carry the source's moving average cost to the receiving outlet. | 1 |
| FR-TRF-005 | Standing orders: recurring transfer requests by weekday. | 3 |
| FR-TRF-006 | Optional internal transfer pricing when outlets are separate legal entities (see Q-006). | 3 |

## SAL. Sales and POS

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-SAL-001 | Channels: dine-in, takeaway, each delivery platform, wholesale. Channels are configurable per tenant. | 1 |
| FR-SAL-002 | Manual daily sales entry: per outlet, business date and channel, a grid of menu items and quantities (and platform totals) that creates sales documents and triggers recipe consumption. | 1 |
| FR-SAL-003 | A day can be locked after review; locked days change only through reversal with approval. | 1 |
| FR-SAL-004 | Cashier POS: category and search browsing, modifiers, notes, quick re-order, touch-first layout. | 2 |
| FR-SAL-005 | Order lifecycle: open, sent to kitchen, ready, served, paid, closed, void. Orders can be added to until paid. | 2 |
| FR-SAL-006 | Payments: multiple methods per order, split payment, change calculation, tip and service charge handling. | 2 |
| FR-SAL-007 | Discounts and promotions (item, order, percentage, amount) with reason, permission limits and audit. | 2 |
| FR-SAL-008 | Void and refund with reason, approval by rule and audit; stock effect configurable (return to stock or waste). | 2 |
| FR-SAL-009 | Cashier shifts: open with float, record cash in/out, close with count; expected vs actual cash variance report. | 2 |
| FR-SAL-010 | Receipts as PDF or print; Bluetooth thermal printing in Phase 2; network and USB printers later. | 2 |
| FR-SAL-011 | Wholesale/B2B sale with customer, invoice, due date and payment recording. | 3 |
| FR-SAL-012 | Customer records (name, phone) with consent flag; used for reservations and loyalty only. | 3 |
| FR-SAL-013 | Offline order taking with later sync, idempotent by client-generated ID. | 4 |
| FR-SAL-014 | Payment gateway (dynamic QRIS, e-wallet) with webhook reconciliation. | 4 |
| FR-SAL-015 | Delivery-platform integration through an approved partner or direct API where available. | 4 |
| FR-SAL-016 | Loyalty points and vouchers. | 4 |

## TBL. Tables and reservations

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-TBL-001 | Floors and tables per outlet with name, capacity and status: available, occupied, reserved, needs cleaning. | 2 |
| FR-TBL-002 | Opening a table creates a table session; orders attach to the session. Closing payment frees the table to "needs cleaning". | 2 |
| FR-TBL-003 | Move an order to another table; merge and split tables; split bill by item, equal share or amount. | 2 |
| FR-TBL-004 | Live occupancy view of all tables with elapsed time and open amount. | 2 |
| FR-TBL-005 | Reservations: guest name, phone, party size, date and time, expected duration, notes, status (pending, confirmed, seated, completed, no-show, cancelled). | 3 |
| FR-TBL-006 | Conflict detection using table capacity and a configurable default dwell time; suggested tables for a party size. | 3 |
| FR-TBL-007 | Seating a reservation opens a table session. No-shows are tracked per guest. | 3 |
| FR-TBL-008 | Walk-in waitlist with estimated wait. | 3 |
| FR-TBL-009 | Visual floor plan editor. | 3 |
| FR-TBL-010 | Public booking page and reminder messages. | 4 |

## KDS. Kitchen display and printing

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-KDS-001 | Kitchen display shows incoming orders by station with elapsed time and status controls (new, preparing, ready). | 2 |
| FR-KDS-002 | Kitchen order tickets print to stations configured per menu category. | 2 |
| FR-KDS-003 | Delivery-platform orders appear in the same queue with the platform marked. | 2 |
| FR-KDS-004 | Bump and recall; late-order highlighting by configurable threshold. | 2 |

## FIN. Finance

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-FIN-001 | Finance-lite: cash and bank accounts, expense recording by category, petty cash, and a profit and loss view built from sales, HPP and expenses per outlet and period. | 2 |
| FR-FIN-002 | Double-entry general ledger: chart of accounts (Indonesian F&B template, editable), journals, periods, trial balance, balance sheet, cash flow summary. | 3 |
| FR-FIN-003 | Automatic journals from operational events using configurable posting rules: sales, payments, purchases, receipts, production, transfers, waste, adjustments, counts. | 3 |
| FR-FIN-004 | Manual journal entries with approval and attachments. | 3 |
| FR-FIN-005 | Period close and lock; entries into a locked period are blocked. | 3 |
| FR-FIN-006 | Accounts payable and receivable sub-ledgers with aging reports. | 3 |
| FR-FIN-007 | Delivery-platform settlement: sales recorded gross, commission and fees recorded as expense, payouts reconciled against the platform receivable. | 3 |
| FR-FIN-008 | Regional food-and-beverage tax report per outlet and period from collected tax. | 2 |
| FR-FIN-009 | Enabling finance on an existing tenant requires a start date and opening balances; documents dated before the start date are not journaled. | 3 |
| FR-FIN-010 | Budget per outlet and period with actual vs budget view. | 4 |

## RPT. Reports

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-RPT-001 | Daily flash: net sales, orders, average order value, HPP %, per outlet and channel. | 1 |
| FR-RPT-002 | Sales by outlet, channel, category, item, hour and weekday. | 1 |
| FR-RPT-003 | HPP and gross margin per menu item and category. | 1 |
| FR-RPT-004 | Stock valuation, stock movement, expiry, waste and variance reports. | 1 |
| FR-RPT-005 | Purchases by vendor and item with price trend. | 1 |
| FR-RPT-006 | Reports respect outlet scope and permissions, and filter by date range and outlet group. | 1 |
| FR-RPT-007 | Menu engineering: classify items by popularity and margin (star, plowhorse, puzzle, dog). | 3 |
| FR-RPT-008 | Prime cost (HPP plus labor) using manually entered labor cost. | 3 |
| FR-RPT-009 | Scheduled report delivery by email. | 4 |
| FR-RPT-010 | Heavy reports run as background jobs and are cached; the UI shows when data was last computed. | 1 |
| FR-RPT-011 | Sales summary per outlet by day, week, month or custom range (net sales, orders, comparison with the previous period, best days), exportable, so owners can decide how to reward staff under each outlet's own rules. | 1 |
| FR-RPT-012 | Sales by staff member for POS orders (orders, net sales, average order value) per period, restricted to roles with permission. | 2 |

## NTF. Notifications

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-NTF-001 | In-app notification center with unread count; alert rules decide recipients. | 1 |
| FR-NTF-002 | Approval requests appear to approvers and can be acted on from a phone. | 1 |
| FR-NTF-003 | Email notifications for invitations, resets and critical alerts. | 1 |
| FR-NTF-004 | WhatsApp notifications through an approved provider, optional per tenant. | 4 |
| FR-NTF-005 | Web push notifications on installed PWAs. | 3 |

## Cross-cutting requirements

| ID | Requirement | Phase |
| --- | --- | --- |
| FR-X-001 | Every user-facing string comes from translation files. English and Indonesian ship first; adding a language is adding a file. | 0 |
| FR-X-002 | Money, dates, numbers and units format per tenant locale. Times are stored in UTC and shown in the outlet's timezone. | 0 |
| FR-X-003 | Every create and update that clients may retry accepts an idempotency key. | 0 |
| FR-X-004 | Lists support search, sort, filter and pagination without loading all rows. | 0 |
| FR-X-005 | Destructive actions on business documents are reversals, not deletes. | 1 |
| FR-X-006 | The UI adapts to desktop (dense tables), tablet (POS and counting) and phone (dashboards, approvals, counts, receiving). | 0 |
| FR-X-007 | Context help and an in-app changelog. | 3 |

## Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | API response time for typical reads and writes (excluding reports) | p95 under 300 ms on the launch VPS |
| NFR-002 | POS order creation end to end | under 1 s on a normal mobile connection |
| NFR-003 | Availability | 99.5% monthly at launch (single server); improve with scale |
| NFR-004 | Recovery point objective | 24 h at launch; 15 min after WAL archiving is enabled (Phase 2) |
| NFR-005 | Recovery time objective | 4 h |
| NFR-006 | Browsers | Latest two versions of Chrome, Edge, Safari, Firefox; Android Chrome; iOS Safari 16+ |
| NFR-007 | Accessibility | Touch targets at least 44 px; keyboard operable back-office; contrast per WCAG 2.1 AA |
| NFR-008 | Data integrity | Stock and journal postings are atomic with the business document; ledger invariants verified by automated tests |
| NFR-009 | Security | OWASP ASVS Level 2 as the review checklist; see 06 |
| NFR-010 | Observability | Structured logs with request and tenant IDs; error tracking; uptime checks |
| NFR-011 | Maintainability | Module boundaries enforced by automated import checks; migrations reversible where feasible |
