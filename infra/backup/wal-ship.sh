#!/bin/sh
# One pass of WAL shipping (docs/07 section 8, ADR 0.60): point-in-time recovery.
#
# PostgreSQL copies every finished WAL segment into /wal-archive (archive_command in
# compose.prod.yaml, at least every PG_ARCHIVE_TIMEOUT seconds). This script encrypts each one
# with the owner's PUBLIC key, uploads it to <prefix>/wal/ and deletes the local copy only
# after the upload succeeded. Without object storage it keeps WAL locally for
# WAL_LOCAL_DAYS days so the disk cannot fill up.
set -eu

KEY=${BACKUP_PUBLIC_KEY:-/keys/public-key.asc}
WAL_DIR=${WAL_DIR:-/wal-archive}
PREFIX=${BACKUP_PREFIX:-prod}
export GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT

upload() {
  printf 'user = "%s:%s"\n' "$BACKUP_S3_ACCESS_KEY" "$BACKUP_S3_SECRET_KEY" | curl -K - \
    --fail --silent --show-error --retry 3 \
    --aws-sigv4 "aws:amz:${BACKUP_S3_REGION:-auto}:s3" \
    --upload-file "$1" "$BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET/$PREFIX/wal/$(basename "$1")"
}

if [ -z "${BACKUP_S3_ENDPOINT:-}" ]; then
  find "$WAL_DIR" -type f -mtime +"${WAL_LOCAL_DAYS:-2}" -delete
  exit 0
fi

# Oldest first; *.tmp are segments PostgreSQL is still copying in.
for f in $(ls -1tr "$WAL_DIR" 2>/dev/null | grep -v '\.tmp$' || true); do
  src="$WAL_DIR/$f"
  enc="$(mktemp -d)/$f.gpg"
  gpg --batch --yes --trust-model always --recipient-file "$KEY" --encrypt --output "$enc" "$src"
  if upload "$enc"; then
    rm -f "$src"
  else
    echo "WAL upload failed for $f; will retry" >&2
    rm -rf "$(dirname "$enc")"
    exit 1
  fi
  rm -rf "$(dirname "$enc")"
done
date -u +%s > "${BACKUP_DIR:-/var/backups/pos}/wal-last-success"
