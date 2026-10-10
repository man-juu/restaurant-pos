# Security review, Phase 2 (slice 2l, 2026-10-09)

Internal review before Gate 2. Gate 2 still needs an **independent penetration test**: an outside tester, booked by the owner, before the paid launch of Phase 2 features.

Method: three parallel read-only reviews of the Phase 2 code. Every finding was checked against the code end to end, then fixed with a test, or recorded below with the reason it waits.
- Cashier money paths: orders, payments, discounts, voids, refunds, shifts, receipts.
- Sign-in: PIN on shared devices, Sign in with Google, tenant switching.
- Back office: vendor returns and bills, lot trace, finance, tables, kitchen, combos and outlet menus, the prep-list demand provider.

## Fixed

| Severity | Finding | Fix | Test |
| --- | --- | --- | --- |
| High | A PIN sign-in could switch into another business where the same person is owner, skipping 2FA there. A PIN session is created as fully verified, and tenant switching keeps that. | PIN sign-in is refused for anyone holding a 2FA role in any business (`requires_mfa` checks all memberships). | `test_devices.py::test_a_pin_never_replaces_2fa` |
| Medium | A PIN skipped 2FA that a staff member had turned on for themselves. | People with 2FA on are not offered a PIN and cannot use one. | same |
| Medium | `PUT /me/pin` checked the account password with no attempt limit and no audit on failure. | Uses the same lockout counter as the sign-in page; failures audited as `auth.pin_set_failed`. | `test_set_pin_password_guesses_are_throttled` |
| Medium | A cashier could stay inside their discount limit when setting a fixed amount, then remove or lower lines so the amount became up to 100 % of the bill. | Payment checks every discount again on the final order, against the limit of the person who gave it (`discounts.recheck`, `core/access/role_limits.py`). | `test_discount_rechecked_at_payment_when_the_order_shrank` |
| Medium | A bill could take another outlet's receipts, by naming them or through the PO. | Receipts must be at the bill's outlet. | `test_vendor_payables.py` (FR-PUR-008 test) |
| Medium | A credit note could be applied across outlets. | The credit must be from the bill's own outlet. | covered by the same check |

## Low findings, fixed on 2026-10-10

| Finding | Fix | Test |
| --- | --- | --- |
| Refund method not tied to how the order was paid | Refunds go back by a method used on the order; owners and co-owners may choose another | `test_fr_sal_008_refund_needs_another_persons_approval` |
| Idempotency keys replayable by another user | Stored fingerprint is bound to the signed-in user | `test_an_idempotency_key_replays_only_for_the_same_user` |
| Quantity changes and removal of unsent lines not audited | `sales.order.line_qty` and `sales.order.line_remove` audit entries | `test_discount_rechecked_at_payment_when_the_order_shrank` |
| Revoking a device left its PIN sessions alive | Sessions remember their device (migration 0036); revoking ends them, also after a tenant switch | `test_revoking_a_device_ends_its_pin_sessions` |
| Slow PIN guessing (about 480 a day) | After 3 lockouts in a row the PIN is blocked until a manager resets it; owners and managers are notified (migration 0037) | `test_a_pin_guessed_too_often_is_blocked_until_reset` |
| Google sign-in ignored the account lockout | A locked account stays locked for Google sign-in too | covered by the shared lockout check |

## Checked and fine (summary)

- Outlet scope is checked on every route reviewed, and RLS covers every new table.
- Money ledgers are append-only: vendor payments and money transfers are SELECT and INSERT only.
- Row locks protect double payments, double refunds and double credit use.
- Prices and totals come from the server only.
- Tenders must equal the amount due, and change is given on cash only.
- The device lookup function pins `search_path` and returns only minimal columns.
- Device cookies use the `__Host-` prefix, httpOnly and SameSite=Strict.
- OpenID Connect sign-in:
  - uses PKCE, state and nonce;
  - accepts RS256 tokens only, checked against Google's keys, issuer, audience, expiry and a verified email;
  - redirects only to the app's own login page.
- No raw SQL is built with string formatting. Lot search escapes `%` and `_`.
