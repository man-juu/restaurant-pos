# Runbook: incidents

## Site down
1. `https://<app>/health`: 503 means the database is down; no answer means web or API.
2. On the server: `docker compose -p pos-prod -f /opt/restaurant-pos/compose.prod.yaml ps` and `logs --tail 200 <service>`.
3. Recent deploy? Roll back (`deploy.md`). Disk full? `df -h`, prune old images and logs.
4. Database lost or corrupt: `backup-restore.md`, Disaster restore.

## Suspected breach or data leak (docs/06 section 10)
1. **Contain:** revoke sessions (`UPDATE sessions SET revoked_at = now()` as owner), rotate secrets (`rotate-secrets.md`), restrict `ADMIN_ALLOWED_IPS`.
2. **Preserve evidence:** copy logs and the audit log before changing more.
3. **Assess:** which tenants and data; use the audit log and request IDs.
4. **Notify:** affected tenant owners without delay. Indonesian PDP law requires notifying affected people and the authority within 3 × 24 hours of a personal-data breach **(verify current rules)**.
5. **Fix and review:** root cause, a test that would have caught it, an entry in `docs/security-practices.md`.

## Ransomware on the server
Do not pay. Shut the server down, build a new one from the runbooks, restore the last clean backup (backups are encrypted with your key, stored elsewhere and write-only from the server, so the attacker cannot alter them).
