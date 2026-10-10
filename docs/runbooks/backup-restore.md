# Runbook: backups and restore (NFR-004, NFR-005)

## How backups work

- The `backup` container runs `infra/backup/backup.sh` daily at 02:00 WIB (19:00 UTC).
- `pg_dump` → encrypted with **your public key** → uploaded to object storage at **another provider** with a **write-only key**. The server cannot read old backups. It could still overwrite them unless **versioning or object lock** is on, so that setting is required, not optional.
- Prefixes `daily/`, `weekly/` (Sundays), `monthly/` (1st). Set bucket **lifecycle rules**: delete `daily/` after 7 days, `weekly/` after 28, `monthly/` after 180 (`docs/07` section 8).
- **Required:** turn on bucket **versioning** (and object lock if offered). Choose a storage provider that supports versioning.
- Alert if no new backup appears for 26 hours (`monitoring.md`).
- The last 3 encrypted files also stay on the server for quick restores.
- The dump runs as `pos_backup`: it can read every table of every tenant (`pg_read_all_data` plus BYPASSRLS, so the dump is complete) but cannot change anything. Restores use the owner role.
- **Database created before 2026-10-09** (the role is made by `infra/db/init` only on a new volume): create it once as the owner, with the password from `prod.env`:
  `docker compose -p pos-prod --env-file /etc/restaurant-pos/prod.env -f /opt/restaurant-pos/compose.prod.yaml exec db psql -U pos_owner -d pos -c "CREATE ROLE pos_backup LOGIN NOSUPERUSER BYPASSRLS PASSWORD '<BACKUP_DB_PASSWORD>'; GRANT pg_read_all_data TO pos_backup;"`

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
5. Target: back online within 2 hours. With WAL archiving (below), at most the last 5 minutes of data are lost; from a nightly dump alone, up to 24 hours.

## Uploaded files (photos, attachments)

Each backup run also writes `pos-<prefix>-<stamp>.uploads.tar.gpg`: an encrypted tar of the `uploads` volume, uploaded next to the database dump. Restore after the database:

```
gpg --batch --decrypt pos-prod-<stamp>.uploads.tar.gpg | docker run --rm -i -v restaurant-pos_uploads:/u alpine tar -C /u -xf -
```

Photos are referenced by id from the database, so restore the dump and the uploads tar from the same night.

## Point-in-time recovery (WAL archiving, ADR 0.60)

Use this to go back to a moment before a mistake (for example, data deleted at 14:05: restore to 14:04), or to lose at most about 5 minutes after a server loss.

How it works:
- PostgreSQL copies every finished WAL segment into the `wal-archive` volume, at least every 5 minutes (`PG_ARCHIVE_TIMEOUT`, seconds).
- The `backup` container encrypts each one with your public key and uploads it to `<prefix>/wal/`. The local copy is deleted only after the upload succeeded.
- Every Sunday, and on the first start, it also uploads a physical **base backup** to `<prefix>/base/` (`pg_basebackup`, encrypted). WAL can only be replayed on top of one.
- Without object storage, WAL is kept locally for 2 days only (`WAL_LOCAL_DAYS`), so the disk cannot fill.
- Lifecycle rules to add on the bucket: delete `base/` after 35 days and `wal/` after 35 days. That keeps at least 4 weekly base backups and the WAL between them.
- Monitoring: alert if `wal-last-success` in the backup volume is older than 15 minutes, or `base-last-success` is older than 8 days.

**Database created before 2026-10-09:** give the backup role replication once, then restart the database:

```
docker compose -p pos-prod --env-file /etc/restaurant-pos/prod.env -f /opt/restaurant-pos/compose.prod.yaml exec db sh -c \
  "psql -U pos_owner -d pos -c 'ALTER ROLE pos_backup REPLICATION' && echo 'host replication pos_backup all scram-sha-256' >> \$PGDATA/pg_hba.conf"
docker compose -p pos-prod --env-file /etc/restaurant-pos/prod.env -f /opt/restaurant-pos/compose.prod.yaml restart db backup
```

Restore to a point in time (on your computer or a recovery server, which has the private key):
1. Download the newest `base/` file from **before** the target time, and every `wal/` file from that day on, into one folder (for example `wal/`).
2. `sh infra/backup/pitr-restore.sh pos-prod-<stamp>.base.tar.gpg wal/ /path/to/empty-data-dir "2026-10-09 14:04:00+07"`
   Leave out the time to replay everything (after a server loss).
3. Start PostgreSQL 17 on that data directory, for example
   `docker run -d --name pitr -v /path/to/empty-data-dir:/var/lib/postgresql/data -v "$PWD/wal":"$PWD/wal":ro -v "$GNUPGHOME":/gnupg -e GNUPGHOME=/gnupg postgres:17-alpine`
   (the image needs `gpg`: `docker exec pitr apk add gnupg` before it starts replaying, or use a recovery host with PostgreSQL and gpg installed).
4. It replays WAL up to the time and opens. Check row counts, run the integrity queries from `restore.sh` and `python -m app.admin.cli invariants-job` against it.
5. Then either dump the needed rows into production, or (after a server loss) make it the new production database.

If the log says "recovery ended before configured recovery target was reached", the target is later than the newest uploaded WAL. Leave out the time to replay up to the newest WAL.

First deploy check (staging): after `up -d`, wait 6 minutes, then `docker compose ... exec backup ls /wal-archive` (should be empty or nearly so) and look for `wal/` and `base/` files in the bucket. The container wiring (entrypoint, volume ownership) was checked with `docker compose config` but not run, because the build sandbox has no Docker daemon.

Drill (2026-10-09, PostgreSQL 16 locally, the exact scripts in `infra/backup`):
- A base backup was taken, then 50 rows were added. The time was noted, then 25 more rows were added.
- The WAL was shipped encrypted to a fake bucket (no plaintext in the uploads), and the local archive was emptied after upload.
- `pitr-restore.sh` was run to the noted time. Result: 150 rows, exactly the state at the target (175 existed at the end).
