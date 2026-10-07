#!/bin/sh
# Restore drill and disaster restore (docs/runbooks/backup-restore.md, NFR-005).
#
#   restore.sh <encrypted-backup-file> <target-database>
#
# Needs the PRIVATE key imported into gpg (run on the owner's machine or a recovery host,
# never left on the production server) and PG* variables for a role allowed to create the
# target database. Restores into a scratch database, then checks integrity.
set -eu
FILE=$1
TARGET=$2

createdb "$TARGET"
gpg --batch --decrypt "$FILE" | pg_restore --no-owner --no-privileges --dbname "$TARGET"

echo "Integrity checks on $TARGET:"
psql --no-psqlrc -v ON_ERROR_STOP=1 -d "$TARGET" -At <<'SQL'
SELECT 'alembic revision: ' || version_num FROM alembic_version;
SELECT 'tenants: ' || count(*) FROM tenants;
SELECT 'users: ' || count(*) FROM users;
SELECT 'audit entries: ' || count(*) FROM audit_log;
-- Every membership must point at an existing tenant, user and role.
SELECT CASE WHEN count(*) = 0 THEN 'memberships: ok' ELSE 'memberships: BROKEN ' || count(*) END
FROM memberships m
LEFT JOIN tenants t ON t.id = m.tenant_id
LEFT JOIN users u ON u.id = m.user_id
LEFT JOIN roles r ON r.id = m.role_id
WHERE t.id IS NULL OR u.id IS NULL OR r.id IS NULL;
-- Ledger invariants (stock, journals) are added here with their modules in Phase 1.
SQL
echo "Restore of $FILE into $TARGET finished."
