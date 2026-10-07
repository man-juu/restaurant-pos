#!/bin/sh
# Runs backup.sh once a day at about BACKUP_HOUR_UTC (default 19:00 UTC = 02:00 WIB, outside
# service hours). A failure is logged and retried the next day; monitoring watches
# last-success (docs/runbooks/monitoring.md).
HOUR=${BACKUP_HOUR_UTC:-19}
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "@$(( (now / 86400) * 86400 + HOUR * 3600 ))" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  sh /backup/backup.sh || echo "backup FAILED at $(date -u)" >&2
done
