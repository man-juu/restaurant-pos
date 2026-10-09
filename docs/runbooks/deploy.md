# Runbook: deploy and roll back

## Normal release

1. Merge to `main` with CI green.
2. Tag: `git tag v0.2.0 && git push origin v0.2.0`. The **Release** workflow builds the images, pushes them to GHCR, deploys to **staging** and runs an OWASP ZAP baseline scan.
3. Check staging yourself (sign in, the changed screens).
4. GitHub → Actions → **Deploy production** → Run workflow → tag `v0.2.0`. That click is the approval.
5. `deploy.sh` pulls, migrates, restarts and checks `/health` for up to 2.5 minutes. If unhealthy it **rolls back automatically** to the previous tag and the workflow fails.

Deploy outside peak hours (not 11:00 to 14:00 or 17:00 to 21:00 WIB).

## Manual rollback

```sh
ssh you@server
sudo /opt/restaurant-pos/deploy.sh prod v0.1.9     # any earlier tag
```
Migrations are expand-then-contract, so an older release runs on the newer schema. Never downgrade the database in production; fix forward with a new migration.

## Check what is running

`cat /opt/restaurant-pos/.deployed-prod` and `docker compose -p pos-prod -f /opt/restaurant-pos/compose.prod.yaml ps`.

## One-time steps for servers set up before 2026-10-09

1. Add `BACKUP_DB_PASSWORD=<openssl rand -hex 24>` to `/etc/restaurant-pos/<env>.env` (the compose file now refuses to start without it).
2. Create the read-only backup role once (command in `backup-restore.md`, "Database created before 2026-10-09").
3. Deploy as usual. The migrate step now also runs `python -m app.admin.cli sync-roles`, so existing businesses get the permissions of modules released since they were created.
