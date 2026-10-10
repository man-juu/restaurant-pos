# Data inventory

Required by `docs/06` (personal data protection). List every place that stores personal or sensitive data. Update this in the same slice that adds the data.

| Data | Category | Where stored | Purpose | Retention | Who can access | Added in slice |
| --- | --- | --- | --- | --- | --- | --- |
| User email and name | Personal | `users` | Sign-in, invitations | While the account exists | Identity service; tenant owners see their members | 0.3 |
| Password hash, TOTP secret (AES-GCM encrypted) | Credential | `users` | Authentication | While the account exists | Identity service only; never logged | 0.3, 0.4b |
| Recovery codes (SHA-256), password reset tokens (SHA-256) | Credential | `recovery_codes`, `password_resets` | 2FA recovery, password reset | Until used or expired; pruned by a job later | Identity service only | 0.4b |
| Invitee email | Personal | `invitations` | Staff invitation (FR-IDN-006) | Until accepted or expired | Owner, co-owner | 0.4b |
| Sessions: IP address and user agent | Personal (IP) | `sessions` | Session list and revocation (FR-IDN-007), security review | 30 days after expiry (`docs/05` section 7) | The user (own sessions); identity service | 0.4a |
| Sign-in failure counters | Pseudonymous (hashed email and IP) | `auth_throttle` | Lockout (FR-IDN-003) | Until the lock expires and the counter is cleared | Identity service only | 0.4a |
| Audit entries with user ID, IP and request ID | Personal (IP) | `audit_log` | Security and financial accountability | Same as ledgers (`docs/05` section 7) | Owner, co-owner, users with permission | 0.3 |

| Customer name, phone, note (`customers`) | Reservations, waitlist, later wholesale and loyalty | Tenant staff with `tenant.customer.view` | Until erased on request (`DELETE /api/v1/customers/{id}` blanks name, phone and note; history kept anonymous). Consent time recorded. Never in the audit log. |

Planned entries (fill in when built): device records (Phase 2).
