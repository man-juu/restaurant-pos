# Phase 4 task list (reach)

Order by demand (docs/08 section 6). Owner direction (2026-10-10): the main purpose is stock
(restock, days of inventory, alerts, planning, forecast), simple sales records (income, stock
out by recipe), purchases (spend, restock) from vendors and from the central kitchen (requests
it can edit or reject), cost of goods and receiving. Keep finance simple; every module can be
switched per outlet. Gate 4: offline scenario tests pass (network cut mid-order, resync without
duplicates); gateway reconciliation matches settlements.

| # | Slice | Requirements | Status |
| --- | --- | --- | --- |
| 4a | Offline order taking: server sync API, till totals | FR-SAL-013 | in progress (server done; till screen next) |
| 4a+ | Modules per outlet by the owner; simple and advanced finance; central kitchen notified of requests | FR-TEN-003, FR-FIN, FR-TRF-001 | done 2026-10-10 |
| 4b | Budgets per outlet and period, actual vs budget | FR-FIN-010 | |
| 4c | Import delivery-platform sales files with a saved column mapping | FR-IMP-004 | |
| 4d | Loyalty points and vouchers | FR-SAL-016 | |
| 4e | Scheduled report email | FR-RPT-009 | needs an email provider (Q-005 domain) |
| 4f | Public booking page and reminders | FR-TBL-010 | |
| 4g | Payment gateway (QRIS, e-wallet) | FR-SAL-014 | needs owner choice of provider |
| 4h | WhatsApp notifications | FR-NTF-004 | needs owner choice of provider |
| 4i | Delivery-platform integration | FR-SAL-015 | partner only |
