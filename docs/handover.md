# Handover (2026-10-08)

Paste the message below into a new Claude Code session opened in the repo root.

---

You are continuing development of this Restaurant POS / ERP. Read CLAUDE.md first and follow it exactly; all specs are in docs/. Then read docs/tasks/phase-1.md and the docs/09 changelog entries 0.21 to 0.26.

Branch: `claude/restaurant-pos-project-acc8ep` (PR #1). Pushing to this branch is allowed. Do NOT merge any PR; the owner merges.
Commits: author "Michael Julian" only; no co-author or AI attribution lines. Conventional Commits, one commit per slice.

## Done

- Phase 0 complete.
- 1a tenant settings.
- 1b part 1 catalog backend; part 2 channels and list prices with start dates (migration 0008); part 5 catalog screens.
- 1c recipes: draft/active versions with start dates, nesting with cycle check, expansion to ingredients, cost and margin per channel (migration 0009). Cost comes from a cost source the inventory module registers (`catalog/costing.set_cost_source`).
- 1e inventory ledger: new `inventory` module (depends on catalog, uses only `catalog/interface.py`). One posting engine in `inventory/service.py` (`receive`, `consume`, `reverse`) is the only writer of the ledger; every later document must call it inside its own transaction. Batches, FEFO, moving average per outlet, balances, valuation at a date, opening stock, negative-stock policy setting (`stock.negative_stock`), stock screen (migration 0010).
- 1i waste logs, adjustments, stock counts (full/spot/cycle/blind) with approval rules and no self-approval; shared flow helpers in `inventory/flow.py` (migration 0011).
- Dev fixes: `.gitattributes` forces LF; dev web image copies `.npmrc`; Alembic `env.py` imports inventory models.

State at handover: 165 backend tests, 23 frontend unit tests, 39 Playwright tests (phone, tablet, desktop), all green; lint, mypy, import-linter, complexipy and bundle budget pass. Everything is pushed.

## Owner decisions (2026-10-08, docs/09 entry 0.26)

- Approved dependencies: **Pillow** (image type check and re-encode; must be free and configured safely: pixel limit against decompression bombs, allow-list JPEG/PNG/WebP, re-encode everything, no SVG; record the check in docs/security-practices.md), a **PDF library** (ReportLab proposed) for purchase orders and delivery notes, **openpyxl** for XLSX import/export. Follow the supply-chain rules in CLAUDE.md and docs/security-practices.md (exact versions, 7-day cooling-off, audit).
- Food-cost alert (FR-CAT-012) approved, not urgent: add a target food cost % per item plus a tenant default; build it with the notification center (1j).
- Recipe `waste_pct` stays optional, default 0; it means the share lost in preparation (stock used = qty / (1 - waste %)).
- "Perishable" = the item has a shelf life; expiry is required on purchase receipt, production output and opening stock.

## Owner's case (reference scenario: Korean cloud kitchen)

- A. Supplied by the main kitchen (meat, sauces, noodles, soups): frozen, fixed packs (for example one 150 g pack per portion). Count in packs, expiry dated, exact stock. Nothing new needed: unit "pack", recipe line "1 pack".
- B. Bought locally from changing vendors (rice, milk, onion, cooking oil, gas; eggs are countable): hard to measure, corrected by occasional manual adjustment.
- C. Packaging: countable, does not spoil.

## Waiting for the owner (do not build until answered; each adds columns beyond docs/05)

1. Per-item tracking mode: exact / estimated / not tracked. "Estimated" items never block a sale or raise negative-stock alerts and get a one-tap "set what is on hand" correction.
2. Optional standard cost per item, used when the ledger has no average (gas, or before the first purchase), so one such line does not make a whole recipe cost unknown.
3. Expiry date pre-filled from shelf life on quick purchases.

Ask the owner about these three at the start; continue with the next slice meanwhile.

## Next, in this order

1. 1b part 3: upload engine with Pillow (menu and ingredient photos, login background, later waste photos and invoice attachments); optional by default.
2. 1b part 4: free AI images with usage counter, block at 85 % of the free limit plus per-tenant daily cap (ADR-022); off until the platform configures a key.
3. 1d: import/export CSV/XLSX (items, recipes, vendors, opening stock) and a fictional demo seed shaped like the reference scenario.
4. 1f: purchasing (vendors, PR, PO, receiving, quick purchase, PDF, invoice attachment). Receiving posts through `inventory.service.receive`.
5. 1g production, 1h transfers, 1j stock levels, alerts, notification center (include FR-CAT-012, negative-stock and expiry alerts, nightly invariant job), 1k manual daily sales, 1l reports, 1m, 1n.

Open follow-ups: permission backfill command for existing tenants (new inventory permissions reach only new tenants); pin images and actions by digest; dedicated backup DB role.

## How to run checks without local Python 3.12 or browsers

See the container commands in CLAUDE.md ("Without a local Python 3.12 or browsers"). After backend API changes: `python -m app.openapi ../frontend/src/lib/api`, then `npm run api:generate`; CI fails on drift.

Every change: security check and performance check before push; update docs/security-practices.md and the docs/09 changelog. Ask the owner before new dependencies beyond those approved above, data-model changes beyond docs/05, or destructive actions.

The owner reads on a phone: keep replies short, details in files.
