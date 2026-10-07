# Existing code review (Q-001)

Reviewed: branch `legacy-review` (Korean POS, React 19 + sql.js + Electron/Tauri), 2026-10-07.

## Verdict

**Rewrite, keep as reference.** The legacy app is a single-device offline app (SQLite in the browser's IndexedDB, no server, no sign-in). The approved design (docs/04, ADRs) is a multi-tenant server with PostgreSQL, RLS, roles and audit. The two cannot be merged; porting code would cost more than rebuilding. Its domain knowledge and screens are valuable and are reused below.

## Keep (reuse as input)

| What | Where | Reuse in |
| --- | --- | --- |
| 54 menus, 45 ingredients, full BOM | `src/data/seed-data.js` | demo tenant seed and an import sample (slices 1b-1d) |
| Reorder logic: lead time, min days-of-inventory, daily average usage | `src/services/index.js`, `ingredients.lead_time/min_doi` | reorder suggestions (FR-INV / FR-PUR) |
| Batch stock with expiry | `stock_batches` | already in spec as FEFO lots |
| Trash / restore for deleted master data | `src/services/trash.js` | archive instead of delete (spec) |
| Tables screen, category tabs, POS layout ideas | `src/pages/*`, screenshots | Phase 2 POS screens |
| EN/ID/KO strings | `src/i18n.js` | wording reference |

## Problems found (why not port)

High
1. **Checkout is not atomic.** The sale is saved first, then each item, then stock is checked and deducted one item at a time, saving to disk after each step. "Insufficient stock" on item 2 leaves a saved sale with item 1 deducted and item 2 not. Stock check is per item, so two items using the same ingredient can both pass and drive stock negative. (New design: one database transaction per document.)
2. **Auto-update points at a GitHub repo you don't own** (`koreanpos/koreanpos`) and the app is unsigned. Whoever controls that repo name could ship an "update" that runs on every till. If any copy is installed somewhere, disable auto-update or uninstall it.
3. **No sign-in or roles.** Anyone at the till can delete sales, edit stock or wipe data.
4. **Ledger can be erased.** Permanent delete removes stock transactions; `total_qty` can be edited directly and drift from batches.

Medium
5. Quantities are floating point (`REAL`); rounding errors accumulate. (New: `numeric(18,4)`.)
6. Data lives in browser storage on one PC: clearing site data or a disk failure loses everything; backups are manual.
7. Electron 28 is end-of-life; `sandbox: false`; any link opens via `shell.openExternal` without an https allow-list.
8. Two desktop shells (Electron and Tauri) maintained side by side.

Low
9. Repo hygiene: part of `node_modules`, many screenshots, and debug scripts (`check_regex*.cjs`, `test-*.cjs`) are committed; several near-duplicate pages (`Menu2`, `MenuTest*`).
10. No automated tests.

## Next

- Nothing from this branch is merged. Keep `legacy-review` as an archive (or delete it later; owner decides).
- Seed data and reorder rules are pulled into Phase 1 slices with tests.

## Ideas carried forward (before deleting the legacy branches)

Screens and notes reviewed: POS screens (light/dark, tablet, phone), stock, analytics, settings, the reference POS screenshots the owner collected, and the legacy ADR, design-token and tech-debt notes.

POS screen (Phase 2, docs/ux-review.md applies):
- Photo grid of menu items with price on the card, category tabs across the top, search box; cart fixed on the right (bottom sheet on phone).
- Cart lines with +/− and remove; subtotal, discount, tax, total; big Pay button; Hold order and Return order as secondary actions.
- Table number on the order header; "online/offline" indicator.
- Fix seen in legacy screens: long names were cut to "2 Spic..."; show two lines and a placeholder icon when there is no photo; never put a date picker on the cart (business date comes from the outlet).

Back office:
- Type-to-confirm for destructive actions and a Trash with restore (we archive instead of delete).
- Stock list with status badges (OK, low, out) and days of inventory; reorder hints from lead time and minimum days of inventory.
- Analytics: daily sales line chart, top items, average order value.

Data:
- Real sample menu (Korean restaurant: sets, rice bowls, ala carte, soups, add-ons; about 54 menus, 45 ingredients with recipes) stays with the owner; it is business data, so it is not committed. A fictional demo seed with the same shape is created in slice 1d.

Not carried forward: client-side SQLite, Electron/Tauri shells, glassmorphism and 3D toggles (hurt contrast and speed on cheap tablets).
