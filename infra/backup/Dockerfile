# Backup job image: PostgreSQL client tools plus gpg (encryption) and curl (S3 upload).
FROM postgres:17-alpine
RUN apk add --no-cache gnupg curl
COPY backup.sh backup-loop.sh restore.sh /backup/
RUN mkdir -p /var/backups/pos && chown postgres:postgres /var/backups/pos
USER postgres
ENTRYPOINT ["/bin/sh", "/backup/backup-loop.sh"]
