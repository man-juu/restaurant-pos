# Backup job image: PostgreSQL client tools plus gpg (encryption) and curl (S3 upload).
FROM postgres:17-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
RUN apk add --no-cache gnupg curl
COPY backup.sh backup-loop.sh restore.sh /backup/
RUN mkdir -p /var/backups/pos && chown postgres:postgres /var/backups/pos
USER postgres
ENTRYPOINT ["/bin/sh", "/backup/backup-loop.sh"]
