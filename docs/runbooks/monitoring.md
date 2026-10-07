# Runbook: monitoring checklist (free tiers)

| Signal | How | Alert when |
| --- | --- | --- |
| Uptime | Free external monitor on `https://<app>/health` (keyword `"ok"`) every 1 to 5 min | Down for 2 minutes |
| Certificate and domain expiry | Same monitor's SSL and domain checks | Under 14 days |
| Backups | Monitor the backup container's log line `uploaded`, or check the storage console daily for a new file in `daily/` | No new backup in 26 hours |
| Disk, memory, CPU | VPS provider graphs and alerts | Disk over 80 %, memory over 85 % |
| Errors | `docker compose logs api` (JSON, with request IDs); an error tracker with personal-data scrubbing can be added later | Spikes of 5xx |
| Security events | Audit log: failed sign-ins, lockouts, admin actions | Lockout spikes |

Weekly (5 minutes): look at the uptime history, the newest backup file, disk use and `docker compose ps`. Monthly: the restore drill.
