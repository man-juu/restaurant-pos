#!/bin/sh
# Nightly encrypted backup (docs/07 section 8, NFR-004).
#
# 1. pg_dump in custom format (compressed, restorable table by table).
# 2. Encrypt with the owner's PUBLIC key: the server can create backups but cannot read them,
#    so a hacked server does not leak old data and ransomware cannot quietly decrypt them.
# 3. Upload to S3-compatible storage at another provider with a write-only key (the server
#    cannot delete or overwrite old backups). Uses curl's built-in AWS SigV4: no extra tools.
# 4. Keep the last 3 encrypted files locally for fast restores.
#
# Retention (7 daily, 4 weekly, 6 monthly) is enforced by bucket lifecycle rules on the
# daily/, weekly/ and monthly/ prefixes (runbook: docs/runbooks/backup-restore.md).
set -eu

KEY=${BACKUP_PUBLIC_KEY:-/keys/public-key.asc}
OUT_DIR=${BACKUP_DIR:-/var/backups/pos}
PREFIX=${BACKUP_PREFIX:-prod}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$OUT_DIR/pos-$PREFIX-$STAMP.dump.gpg"

mkdir -p "$OUT_DIR"
export GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT

pg_dump --format=custom --no-owner --no-privileges \
  | gpg --batch --yes --trust-model always --recipient-file "$KEY" --encrypt --output "$FILE"
SIZE=$(wc -c < "$FILE")
[ "$SIZE" -gt 1024 ] || { echo "backup suspiciously small ($SIZE bytes)" >&2; exit 1; }

upload() {
  # Credentials go in through stdin (-K -), so they never appear in the process list.
  printf 'user = "%s:%s"\n' "$BACKUP_S3_ACCESS_KEY" "$BACKUP_S3_SECRET_KEY" | curl -K - \
    --fail --silent --show-error --retry 3 \
    --aws-sigv4 "aws:amz:${BACKUP_S3_REGION:-auto}:s3" \
    --upload-file "$FILE" "$BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET/$PREFIX/$1/$(basename "$FILE")"
}

if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
  upload daily
  [ "$(date -u +%u)" = 7 ] && upload weekly    # Sundays
  [ "$(date -u +%d)" = 01 ] && upload monthly  # first of the month
  echo "uploaded $(basename "$FILE") ($SIZE bytes)"
else
  echo "WARNING: BACKUP_S3_ENDPOINT not set; backup kept locally only: $FILE" >&2
fi

# Local copies: keep the newest 3.
ls -1t "$OUT_DIR"/pos-"$PREFIX"-*.dump.gpg | tail -n +4 | xargs -r rm -f
date -u +%s > "$OUT_DIR/last-success"
