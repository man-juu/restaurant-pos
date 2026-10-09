#!/bin/sh
# Weekly physical base backup (ADR 0.60). WAL can only be replayed on top of a physical copy
# of the data directory, so point-in-time recovery = newest base backup before the target
# time + every WAL segment after it. Tar format with the WAL needed to make it consistent
# (-X fetch), encrypted with the owner's PUBLIC key, uploaded to <prefix>/base/.
set -eu

KEY=${BACKUP_PUBLIC_KEY:-/keys/public-key.asc}
OUT_DIR=${BACKUP_DIR:-/var/backups/pos}
PREFIX=${BACKUP_PREFIX:-prod}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$OUT_DIR/pos-$PREFIX-$STAMP.base.tar.gpg"
export GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT

pg_basebackup --pgdata=- --format=tar --wal-method=fetch --checkpoint=fast --no-password \
  | gpg --batch --yes --trust-model always --recipient-file "$KEY" --encrypt --output "$FILE"
SIZE=$(wc -c < "$FILE")
[ "$SIZE" -gt 1024 ] || { echo "base backup suspiciously small ($SIZE bytes)" >&2; exit 1; }

if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
  printf 'user = "%s:%s"\n' "$BACKUP_S3_ACCESS_KEY" "$BACKUP_S3_SECRET_KEY" | curl -K - \
    --fail --silent --show-error --retry 3 \
    --aws-sigv4 "aws:amz:${BACKUP_S3_REGION:-auto}:s3" \
    --upload-file "$FILE" "$BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET/$PREFIX/base/$(basename "$FILE")"
  echo "uploaded base backup $(basename "$FILE") ($SIZE bytes)"
fi
# Keep only the newest base backup locally (they are large).
ls -1t "$OUT_DIR"/pos-"$PREFIX"-*.base.tar.gpg | tail -n +2 | xargs -r rm -f
date -u +%s > "$OUT_DIR/base-last-success"
