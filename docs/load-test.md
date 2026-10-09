# Load test record (Gate 1, NFR-001)

Date: 2026-10-09. Tool: k6 v0.54.0. Script: `backend/tests/load/backoffice.js`, seed: `backend/tests/load/seed.py`.

## Setup

- API: `uvicorn --workers 2` (as in the production image), PostgreSQL 16, app role with RLS, on one 4 vCPU, 15 GB sandbox machine that also ran k6. The launch VPS has 2 cores and 4 GB, so treat these numbers as an upper bound and expect roughly half the throughput there.
- Data: one tenant, one outlet, 40 ingredients, 30 menu items with recipes, a delivery channel with prices, opening stock and 60 days of daily sales (about 900 sales lines, 3 600 stock movements) before the run.
- Mix per action: 25 % capabilities, 15 % unread notifications, 15 % stock list (with days left), 15 % catalog items, 10 % sales day, 8 % waste entry (typical write), 4 % daily sales entry (bulk write: replaces a channel-day, about 20 ingredient lines out of stock), 8 % sales summary report (30 days).
- Think time 1 to 3 s per user action (THINK=0 for stress runs). Ramp 20 s, hold 60 s.

## Results (p95)

| Users (all on one outlet) | Reads | Typical writes | Daily sales entry | Reports | Errors |
| --- | --- | --- | --- | --- | --- |
| 60, with think time | 99 ms | 184 ms | 576 ms | 52 ms | 0 % |
| 120, with think time | 167 ms | 502 ms | 2.79 s | 175 ms | 0 % |
| 5, no think time (≈ 42 req/s) | 74 ms | (bulk only) 1.67 s | – | 38 ms | 0 % |
| 30, no think time (≈ 68 req/s, CPU bound) | 352 ms | 648 ms | 13.7 s | 297 ms | 0 % |

NFR-001 (p95 under 300 ms for typical reads and writes) holds at 60 concurrently active users on one outlet; reads and reports still hold at 120. The limit is writes to the same outlet, which queue on that outlet's number counter and stock rows (by design: gapless numbering and an exact ledger). Several outlets or tenants spread this.

## Found and fixed during the run

- **Deadlock between concurrent daily sales entries** (5 % of entries failed with HTTP 500 in the first run): an entry reversed its earlier stock (locking stock rows) before taking the document number counter, while another held the counter and waited for stock. Fixed by taking the number first; every posting now locks counter, then stock. Re-run: 0 errors.

## Follow-ups

- Daily sales entry is the heaviest write (one ledger row and balance update per ingredient line, plus the reversal of the entry it replaces). If pilots enter many channels at once, batch the ledger writes (one INSERT for all movements).
- Transfer receiving with losses allocates the adjustment number after posting stock; same lock-order pattern, much rarer. Move the number allocation first when touching that code.
- Re-run on the real VPS during the pilot and record the numbers here (Gate 1).
