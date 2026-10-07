# Data inventory

Required by `docs/06` (personal data protection). List every place that stores personal or sensitive data. Update this in the same slice that adds the data.

| Data | Category | Where stored | Purpose | Retention | Who can access | Added in slice |
| --- | --- | --- | --- | --- | --- | --- |
| User email and name | Personal | `users` | Sign-in, invitations | While the account exists | Identity service; tenant owners see their members | 0.3 |
| Password hash, TOTP secret (encrypted) | Credential | `users` | Authentication | While the account exists | Identity service only; never logged | 0.3 (columns), 0.4 (use) |
| Audit entries with user ID, IP and request ID | Personal (IP) | `audit_log` | Security and financial accountability | Same as ledgers (`docs/05` section 7) | Owner, co-owner, users with permission | 0.3 |

Planned entries (fill in when built): session and device records with IP and user agent (0.4), customer name and phone (Phase 3).
