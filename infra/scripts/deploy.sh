#!/bin/sh
# Deploy one release on the server (docs/07 section 7). Run by the pipeline over SSH:
#   sudo /opt/restaurant-pos/deploy.sh <staging|prod> <tag>
# Pulls the immutable images for <tag>, runs migrations, restarts, checks /health and rolls
# back to the previous tag automatically if the new release is unhealthy.
# Migrations are expand-then-contract (CLAUDE.md rule 11), so the previous release still runs
# on the new schema and rollback never needs a database downgrade.
set -eu

ENV_NAME=$1
TAG=$2
case "$ENV_NAME" in staging | prod) ;; *) echo "usage: deploy.sh <staging|prod> <tag>" >&2; exit 2 ;; esac
printf '%s' "$TAG" | grep -Eqx 'v[0-9]+\.[0-9]+\.[0-9]+' || { echo "tag must look like v1.2.3" >&2; exit 2; }

DIR=/opt/restaurant-pos
ENV_FILE=/etc/restaurant-pos/$ENV_NAME.env
STATE=$DIR/.deployed-$ENV_NAME
PREVIOUS=$(cat "$STATE" 2>/dev/null || echo "")
. "$ENV_FILE"  # for APP_DOMAIN; the file is root-owned, mode 600

run() { tag=$1; shift; IMAGE_TAG=$tag docker compose -p "pos-$ENV_NAME" --env-file "$ENV_FILE" -f "$DIR/compose.prod.yaml" "$@"; }

healthy() {
  for _ in $(seq 1 30); do
    if curl --fail --silent --max-time 5 "https://$APP_DOMAIN/health" >/dev/null; then return 0; fi
    sleep 5
  done
  return 1
}

echo "Deploying $TAG to $ENV_NAME (previous: ${PREVIOUS:-none})"
run "$TAG" pull --quiet
run "$TAG" up -d --remove-orphans
if healthy; then
  echo "$TAG" > "$STATE"
  docker image prune --force --filter "until=168h" >/dev/null
  echo "OK: $TAG is live on $ENV_NAME"
  exit 0
fi

echo "UNHEALTHY: $TAG failed its health check" >&2
if [ -n "$PREVIOUS" ]; then
  echo "Rolling back to $PREVIOUS" >&2
  run "$PREVIOUS" up -d --remove-orphans
  healthy && echo "Rolled back to $PREVIOUS" >&2 || echo "ROLLBACK ALSO UNHEALTHY: see docs/runbooks/incident.md" >&2
fi
exit 1
