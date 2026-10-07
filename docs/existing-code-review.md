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
