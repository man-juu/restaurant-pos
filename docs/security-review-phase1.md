# Phase 1 security review (2026-10-09)

Method: one read-only review pass over all Phase 1 routes, looking for tenant and outlet bypass, cost exposure (docs/03 rule 5), injection and unsafe uploads. Then a fix and a regression test for each finding.

| # | Severity | Finding | Fix |
| --- | --- | --- | --- |
| 1 | Medium | Production and transfer responses showed costs to roles without cost view | `show_cost` flag; fields return null; UI hides them (`test_production`) |
| 2 | Medium | An outlet-limited manager could read audit entries of all outlets | Filter on own outlets plus tenant-wide entries (`test_security_review`) |
| 3 | Low | Count-variance and approval notifications showed amounts to non-cost roles | Amounts only for `catalog.cost.view` holders |
| 4 | Low | Receipt reversal did not check outlet scope | Load the receipt and check scope first (404) |
| 5 | Low | Invoice photos could be read by any member | Needs purchasing view plus cost view (404 otherwise) |

No injection, tenant bypass (RLS held in every probe) or authentication issue was found.
