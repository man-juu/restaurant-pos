# Phase 2 task list (front of house and money)

Order follows docs/08 section 4, with modifiers and outlet overrides first (moved from Phase 1, docs/09 0.20). PR #1 stays open until the owner says so.

| # | Slice | Requirements | Status |
| --- | --- | --- | --- |
| 2a | Modifiers (groups, options, price delta, ingredient delta), availability flags | FR-CAT-003 | done 2026-10-09 |
| 2b | POS orders, payments (split, change, tip, cash rounding), cash shifts; stock out on payment | FR-SAL-005, 006, 009 | done 2026-10-09 |
| 2c | Cashier POS screen (touch-first, search, modifiers, notes, re-order), shift screen | FR-SAL-004 | done 2026-10-09 |
| 2d | Discounts with role limits, voids and refunds with approval and stock effect | FR-SAL-007, 008 | done 2026-10-09 (partial refunds later) |
| 2e | Floors, tables, sessions, move, merge, split bill, live occupancy | FR-TBL-001 to 004 | done 2026-10-09 |
| 2f | Kitchen display, stations per category, bump and recall, late highlight, tickets | FR-KDS-001 to 004 | done 2026-10-09 (station ticket printing with 2g) |
| 2g | Receipts PDF, Bluetooth thermal printing (Web Bluetooth, ESC/POS) | FR-SAL-010 | done 2026-10-09 (Bluetooth via Web Bluetooth; network and USB printers later) |
| 2h | Registered devices and PIN sign-in | FR-IDN-004 | done 2026-10-09 |
| 2i | Combos and bundles, per-outlet overrides | FR-CAT-011, FR-TEN-011 | done 2026-10-09 |
| 2j | Finance-lite (accounts, expenses, petty cash, P&L), tax report, sales by staff | FR-FIN-001, 008, FR-RPT-012 | done 2026-10-09 |
| 2k | Lot traceability, vendor returns and credit notes, vendor bills with three-way match, prep sheets PDF | FR-INV-016, FR-PUR-008, 009, FR-PRD-006 | Done (2026-10-09) |
| 2l | WAL archiving, POS load test, security review (Gate 2 needs an independent pentest) | Gate 2 | Done internally (2026-10-09); independent pentest still to book |
