# Runbook: backups and restore (NFR-004, NFR-005)

## How backups work

- The `backup` container runs `infra/backup/backup.sh` daily at 02:00 WIB (19:00 UTC).
- `pg_dump` → encrypted with **your public key** → uploaded to object storage at **another provider** with a **write-only key**. The server cannot read old backups. It could still overwrite them unless **versioning or object lock** is on, so that setting is required, not optional.
- Prefixes `daily/`, `weekly/` (Sundays), `monthly/` (1st). Set bucket **lifecycle rules**: delete `daily/` after 7 days, `weekly/` after 28, `monthly/` after 180 (`docs/07` section 8).
- **Required:** turn on bucket **versioning** (and object lock if offered). Choose a storage provider that supports versioning.
- Alert if no new backup appears for 26 hours (`monitoring.md`).
- The last 3 encrypted files also stay on the server for quick restores.

## Monthly restore drill (required)

On your computer (it has the private key):
1. Download the newest file from `daily/` in the provider's console.
2. Start a throwaway PostgreSQL 17: `docker run -d --name drill -e POSTGRES_PASSWORD=x -p 5499:5432 postgres:17-alpine`
3. `PGHOST=localhost PGPORT=5499 PGUSER=postgres PGPASSWORD=x sh infra/backup/restore.sh <file> drill`
4. All checks must print `ok` and sensible counts. Note the date and result in `docs/runbooks/drill-log.md`, then `docker rm -f drill`.

The procedure was rehearsed during slice 0.8 (2026-10-07): encrypted dump, no readable data in the file, restore into a scratch database, all checks passed.

## Disaster restore (server lost)

1. Create a new server (`server-setup.md`), but do not start `web` yet.
2. Start only the database: `docker compose ... up -d db`.
3. Copy the newest backup and your private key to a **temporary** recovery location, run `restore.sh <file> pos`, then delete the private key from that machine.
4. Deploy the last good tag (`deploy.md`), check sign-in, then switch DNS if the IP changed.
5. Target: back online within 4 hours, losing at most the last 24 hours of data (until WAL archiving in Phase 2).

## Uploaded files (photos, attachments)

Each backup run also writes `pos-<prefix>-<stamp>.uploads.tar.gpg`: an encrypted tar of the `uploads` volume, uploaded next to the database dump. Restore after the database:

```
gpg --batch --decrypt pos-prod-<stamp>.uploads.tar.gpg | docker run --rm -i -v restaurant-pos_uploads:/u alpine tar -C /u -xf -
```

Photos are referenced by id from the database, so restore the dump and the uploads tar from the same night.
