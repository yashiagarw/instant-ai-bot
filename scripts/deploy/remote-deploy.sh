#!/bin/sh
# Deploys one commit's images on a server (Phase 5.6). Run by GitHub Actions over SSH as the deploy user (never root);
# can also be run by hand on the server (docs/runbooks/deploy.md, rollback.md).
#
#   remote-deploy.sh deploy <commit sha>     pull that commit's images, start them (migrations run first), wait healthy
#   remote-deploy.sh rollback                go back to the previous release's images (no migration, no downgrade)
#   remote-deploy.sh status                  current and previous release, and the services
#   remote-deploy.sh limits loadtest|normal  staging only: raise the per-IP limits for a k6 run, then restore them
#
# Layout under APP_ROOT (/opt/autocare, docs/server-setup.md):
#   shared/.env.prod  shared/backend/.env.prod   settings and secrets (only on the server; never in git or GitHub)
#   shared/deploy.env                           IMAGE_REPO (ghcr.io/<owner>), DEPLOY_ENVIRONMENT (staging|production),
#                                               COMPOSE_PROFILES (storage), PRE_DEPLOY_BACKUP (1 on production)
#   shared/data/raw  shared/data/media          the datasets and their pictures
#   releases/<sha>/                             docker-compose.prod.yml, docker/caddy/Caddyfile, scripts (from CI)
#   shared/current  shared/previous             release shas;  shared/deploys.log  one line per action
# Images: <IMAGE_REPO>/autocare-api:<sha>, autocare-backup:<sha>, autocare-web:<env>-<sha>, autocare-admin:<env>-<sha>.
# The server pulls them with its read-only registry login (docker login ghcr.io, done once).
set -eu

APP_ROOT=${APP_ROOT:-/opt/autocare}
SHARED="$APP_ROOT/shared"
PROJECT=autocare-prod   # the volumes (database, photos, backups) belong to this name: never change it
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-420}

[ -f "$SHARED/deploy.env" ] || { echo "missing $SHARED/deploy.env (docs/server-setup.md)" >&2; exit 2; }
# shellcheck disable=SC1091
. "$SHARED/deploy.env"
: "${IMAGE_REPO:?set IMAGE_REPO in $SHARED/deploy.env}" "${DEPLOY_ENVIRONMENT:?set DEPLOY_ENVIRONMENT in $SHARED/deploy.env}"
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-storage}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$SHARED/deploys.log"; }
read_state() { cat "$SHARED/$1" 2>/dev/null || true; }

use_release() {
  sha=$1
  dir="$APP_ROOT/releases/$sha"
  [ -f "$dir/docker-compose.prod.yml" ] || { echo "release $sha is not on this server ($dir)" >&2; exit 2; }
  mkdir -p "$dir/backend"
  ln -sfn "$SHARED/.env.prod" "$dir/.env.prod"
  ln -sfn "$SHARED/backend/.env.prod" "$dir/backend/.env.prod"
  export API_IMAGE="$IMAGE_REPO/autocare-api:$sha"
  export BACKUP_IMAGE="$IMAGE_REPO/autocare-backup:$sha"
  export WEB_IMAGE="$IMAGE_REPO/autocare-web:$DEPLOY_ENVIRONMENT-$sha"
  export ADMIN_IMAGE="$IMAGE_REPO/autocare-admin:$DEPLOY_ENVIRONMENT-$sha"
  export DATA_RAW_DIR="$SHARED/data/raw" DATA_MEDIA_DIR="$SHARED/data/media"
  export SENTRY_RELEASE="$sha"
  DIR=$dir
}

dcp() { docker compose -p "$PROJECT" --project-directory "$DIR" -f "$DIR/docker-compose.prod.yml" --env-file "$SHARED/.env.prod" "$@"; }

wait_healthy() {
  # Every long-running service healthy (compose's own health checks: the API's is /api/health/ready).
  waited=0
  while :; do
    bad=$(dcp ps --format '{{.Service}} {{.Status}}' | grep -v -E '\(healthy\)' | grep -v -E '^(migrate|setup|tools) ' || true)
    [ -z "$bad" ] && return 0
    if [ "$waited" -ge "$HEALTH_TIMEOUT" ]; then
      echo "not healthy after ${HEALTH_TIMEOUT}s:" >&2; echo "$bad" >&2
      dcp logs --tail 60 api worker web admin caddy >&2 || true
      return 1
    fi
    sleep 10; waited=$((waited + 10))
  done
}

migrate_ok() {
  id=$(dcp ps -a -q migrate)
  [ -n "$id" ] || return 0
  code=$(docker inspect -f '{{.State.ExitCode}}' "$id")
  [ "$code" = 0 ] || { echo "migrations failed (exit $code):" >&2; dcp logs --tail 80 migrate >&2; return 1; }
}

deploy() {
  sha=$1
  use_release "$sha"
  current=$(read_state current)
  log "deploy $sha ($DEPLOY_ENVIRONMENT), running: ${current:-none}"
  dcp pull --quiet
  if [ "${PRE_DEPLOY_BACKUP:-0}" = 1 ] && [ -n "$current" ]; then
    # Production: a fresh encrypted backup before the migrations (docs/runbooks/restore.md); skipped (logged) by the
    # backup script itself when no BACKUP_AGE_RECIPIENT is set.
    log "backup before deploy"
    dcp run --rm --no-deps backup backup.sh
  fi
  # `migrate` (alembic upgrade head) runs first; the API and the worker start only if it succeeded.
  dcp up -d --no-build --remove-orphans
  migrate_ok
  wait_healthy
  if [ "$current" != "$sha" ]; then
    [ -n "$current" ] && echo "$current" > "$SHARED/previous"
    echo "$sha" > "$SHARED/current"
  fi
  log "deployed $sha"
  prune
}

rollback() {
  target=$(read_state previous)
  failed=$(read_state current)
  [ -n "$target" ] || { echo "no previous release recorded: deploy a commit by its sha instead" >&2; exit 2; }
  use_release "$target"
  log "rollback from ${failed:-?} to $target ($DEPLOY_ENVIRONMENT)"
  dcp pull --quiet
  # No `migrate`: the previous release's code does not know the newer migrations, and the database is never
  # downgraded automatically (docs/runbooks/rollback.md). Its readiness reports "migrations": "ahead".
  dcp up -d --no-build --no-deps caddy web admin api worker backup
  wait_healthy
  echo "$target" > "$SHARED/current"
  rm -f "$SHARED/previous"   # no ping-pong: a second rollback needs an explicit `deploy <sha>`
  log "rolled back to $target (database left as it is)"
}

prune() {
  # Keep the last 5 release folders and unused images older than 14 days (the registry keeps every tag).
  # shellcheck disable=SC2012
  ls -1t "$APP_ROOT/releases" | tail -n +6 | while read -r old; do
    [ "$old" = "$(read_state current)" ] || [ "$old" = "$(read_state previous)" ] || rm -rf "${APP_ROOT:?}/releases/$old"
  done
  docker image prune -af --filter "until=336h" >/dev/null 2>&1 || true
}

status() {
  echo "environment: $DEPLOY_ENVIRONMENT"
  echo "current:     $(read_state current)"
  echo "previous:    $(read_state previous)"
  cur=$(read_state current)
  if [ -n "$cur" ]; then use_release "$cur"; dcp ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'; fi
  tail -5 "$SHARED/deploys.log" 2>/dev/null || true
}

limits() {
  [ "$DEPLOY_ENVIRONMENT" = staging ] || { echo "limits: staging only (never raise production's limits)" >&2; exit 2; }
  cur=$(read_state current)
  [ -n "$cur" ] || { echo "nothing deployed" >&2; exit 2; }
  use_release "$cur"
  case "$1" in
    loadtest) [ -f "$DIR/docker-compose.loadtest.yml" ] || { echo "release $cur has no docker-compose.loadtest.yml" >&2; exit 2; }
              docker compose -p "$PROJECT" --project-directory "$DIR" -f "$DIR/docker-compose.prod.yml" \
                -f "$DIR/docker-compose.loadtest.yml" --env-file "$SHARED/.env.prod" up -d --no-build --no-deps api ;;
    normal) dcp up -d --no-build --no-deps api ;;
    *) echo "usage: $0 limits loadtest|normal" >&2; exit 2 ;;
  esac
  wait_healthy
  log "limits $1 (api recreated)"
}

case "${1:-}" in
  deploy) [ -n "${2:-}" ] || { echo "usage: $0 deploy <commit sha>" >&2; exit 2; }; deploy "$2" ;;
  rollback) rollback ;;
  status) status ;;
  limits) limits "${2:-}" ;;
  *) echo "usage: $0 deploy <sha> | rollback | status | limits loadtest|normal" >&2; exit 2 ;;
esac
