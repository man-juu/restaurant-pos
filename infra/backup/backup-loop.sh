#!/bin/sh
# Runs backup.sh once a day at about BACKUP_HOUR_UTC (default 19:00 UTC = 02:00 WIB, outside
# service hours), a base backup on BACKUP_BASE_WEEKDAY (1-7, default 7 = Sunday) and at first
# start, and ships WAL every minute in the background (point-in-time recovery, ADR 0.60).
# A failure is logged and retried; monitoring watches the *-last-success files
# (docs/runbooks/monitoring.md).
HOUR=${BACKUP_HOUR_UTC:-19}
OUT_DIR=${BACKUP_DIR:-/var/backups/pos}

if [ "${WAL_ARCHIVE:-on}" = on ]; then
  ( while true; do sh /backup/wal-ship.sh || echo "WAL shipping FAILED at $(date -u)" >&2; sleep 60; done ) &
  [ -f "$OUT_DIR/base-last-success" ] || sh /backup/basebackup.sh || echo "base backup FAILED" >&2
fi

while true; do
  now=$(date -u +%s)
  next=$(date -u -d "@$(( (now / 86400) * 86400 + HOUR * 3600 ))" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  sh /backup/backup.sh || echo "backup FAILED at $(date -u)" >&2
  if [ "${WAL_ARCHIVE:-on}" = on ] && [ "$(date -u +%u)" = "${BACKUP_BASE_WEEKDAY:-7}" ]; then
    sh /backup/basebackup.sh || echo "base backup FAILED at $(date -u)" >&2
  fi
done
