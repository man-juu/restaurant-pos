# Data inventory

Required by `docs/06` (personal data protection). List every place that stores personal or sensitive data. Update this in the same slice that adds the data.

| Data | Category | Where stored | Purpose | Retention | Who can access | Added in slice |
| --- | --- | --- | --- | --- | --- | --- |
| User email and name | Personal | `users` | Sign-in, invitations | While the account exists | Identity service; tenant owners see their members | 0.3 |
| Password hash, TOTP secret (encrypted) | Credential | `users` | Authentication | While the account exists | Identity service only; never logged | 0.3 (columns), 0.4 (use) |
| Sessions: IP address and user agent | Personal (IP) | `sessions` | Session list and revocation (FR-IDN-007), security review | 30 days after expiry (`docs/05` section 7) | The user (own sessions); identity service | 0.4a |
| Sign-in failure counters | Pseudonymous (hashed email and IP) | `auth_throttle` | Lockout (FR-IDN-003) | Until the lock expires and the counter is cleared | Identity service only | 0.4a |
| Audit entries with user ID, IP and request ID | Personal (IP) | `audit_log` | Security and financial accountability | Same as ledgers (`docs/05` section 7) | Owner, co-owner, users with permission | 0.3 |

Planned entries (fill in when built): TOTP secrets and recovery codes in use, invitations and reset tokens (0.4b), device records (Phase 2), customer name and phone (Phase 3).
