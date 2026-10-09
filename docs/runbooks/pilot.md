# Runbook: Phase 1 pilot (Gate 1)

Gate 1 (docs/08): the first tenant's real ingredients, recipes and opening stock are loaded; seven days of real use; stock ledger invariants hold; load test recorded; security review of the phase scope done. The last two are done in development (docs/load-test.md, docs/security-review-phase1.md). This page is the owner's checklist for the rest.

## Before day 1 (about half a day)

1. **Deploy** the release to production (runbooks `server-setup.md`, `deploy.md`), including the one-time steps at the end of `deploy.md`.
2. **Create the business** in the platform console (Businesses, New), profile and plan as agreed; the owner gets an invitation e-mail and sets up two-factor sign-in.
3. **Settings** (owner): outlets, tax and service charge, payment methods, numbering, approval rules (for example purchase orders above Rp 1.000.000 need a manager), stock settings (negative stock, expiry warning days, low-days and count-difference alerts), default food-cost target.
4. **Users**: invite managers, storekeepers, cooks and cashiers with their roles and outlets.
5. **Load the data** with the Excel templates (Catalog, Import; Inventory, Opening stock):
   - Items (ingredients with base unit, shelf life, storage; menu items; semi-finished items), categories created automatically.
   - Recipes (one draft per dish, then review and activate them in the catalog).
   - Prices per channel (dine-in, takeaway, each delivery platform) and the platform item codes on each platform channel.
   - Opening stock per outlet on the start date (count it that morning).
   - Vendors and vendor prices; mark the preferred vendor per item where it matters.
   - Par levels and reorder points for the main items (Inventory, Levels).
   The demo files in `docs/demo/` show the expected columns.

## Days 1 to 7

- Every day: receive purchases (quick purchase or against a PO), record production and transfers if the central kitchen is used, log waste, enter daily sales per channel, lock the day after review.
- Twice in the week: a spot count of the 10 most valuable items; once at the end: a full count.
- Watch the bell: expiring stock, low stock, approvals waiting, count differences, food cost above target.

## Checks at the end of the week

- [ ] Platform console, the business, Usage: **job failures in 7 days = 0** (the nightly invariants job records any ledger break there).
- [ ] Reports: stock variance for the week looks plausible; food cost % per item is near what the owner expects.
- [ ] Stock valuation on the last day matches the full count within the variance the owner accepts.
- [ ] Re-run the load test against the production server outside business hours and add the numbers to `docs/load-test.md`.
- [ ] Collect what was confusing or slow on each screen (`docs/ux-review.md` checklist) for the Phase 2 backlog.

When all boxes are ticked, Gate 1 is passed: record it in `docs/09` with the date.
