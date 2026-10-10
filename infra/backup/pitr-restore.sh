#!/bin/sh
# Point-in-time restore (ADR 0.60, docs/runbooks/backup-restore.md). Run on a RECOVERY host
# that has the owner's PRIVATE key, never on the production server.
#
#   pitr-restore.sh <base.tar.gpg> <dir-with-wal.gpg-files> <data-dir> ["YYYY-MM-DD HH:MM:SS+07"]
#
# Unpacks the base backup into <data-dir> (must be empty) and configures recovery: PostgreSQL
# then decrypts and replays WAL from <dir> up to the target time (or to the end), and stops.
set -eu
BASE=$1
WAL=$(cd "$2" && pwd)
DATA=$3
TARGET=${4:-}

[ -z "$(ls -A "$DATA" 2>/dev/null)" ] || { echo "$DATA is not empty" >&2; exit 1; }
mkdir -p "$DATA" && chmod 700 "$DATA"
gpg --batch --decrypt "$BASE" | tar -C "$DATA" -xf -
{
  echo "restore_command = 'gpg --batch --quiet --decrypt --output %p $WAL/%f.gpg'"
  [ -n "$TARGET" ] && echo "recovery_target_time = '$TARGET'"
  echo "recovery_target_action = 'promote'"
} >> "$DATA/postgresql.auto.conf"
touch "$DATA/recovery.signal"
echo "Ready. Start PostgreSQL on $DATA; it replays WAL ${TARGET:+up to $TARGET }and opens."
echo "Then run the integrity checks: restore.sh's queries, and python -m app.admin.cli invariants-job."
