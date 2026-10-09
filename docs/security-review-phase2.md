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

## Recorded, not fixed yet (low)

- **Refund method:** a refund method is not tied to how the order was paid. A QRIS sale could be refunded as cash from the drawer. Approval rules still apply. Next step: allow only methods used on the order, or require approval when the method differs.
- **Idempotency keys:** keys are per tenant, and the stored answer is replayed before the outlet check. Exploiting this needs a random UUID from another user. Next step: bind the key to the user.
- **Open orders:** quantity changes and removal of unsent lines are not audited. The discount abuse above is now blocked at payment.
- **Device revoke:** revoking a device stops new PIN sign-ins at once, but does not end sessions already opened on it. Those end at the idle timeout (default 60 min). Next step: store the device on the session and revoke them together.
- **PIN guessing:** a patient attacker holding a device cookie can guess about 480 PINs a day, because the 15-minute lock repeats. Next step: lock for good after 3 lockouts until a manager resets, and notify the owner.
- **Google sign-in and lockout:** Google sign-in ignores the password lockout. This is by design, because the lockout stops password guessing, and Google proves identity separately.

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
