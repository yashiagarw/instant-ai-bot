#!/bin/sh
# k6 load test of the diagnosis API (Phase 5.6): loadtest/diagnosis.js, every step p95 < 800 ms. k6 runs in Docker.
#
#   sh scripts/loadtest.sh staging [VUS] [DURATION]   the staging server (needs STAGING_SSH=deploy@<host> to raise its
#                                                    per-IP limits for the run, then restore them); domains from
#                                                    STAGING_API_DOMAIN / STAGING_WEB_DOMAIN (defaults below)
#   sh scripts/loadtest.sh local [VUS] [DURATION]     the local production stack (docker-compose.prod.local.yml,
#                                                    https://localhost): numbers NOT representative of a server
#   sh scripts/loadtest.sh <api url> <web origin> [VUS] [DURATION]   anything else; its limits must already allow it
#
# VUS default 200, DURATION (at full load) default 5m. Results: loadtest/results/<target>-<time>.json (+ the console).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
K6_IMAGE=grafana/k6:1.3.0
target=${1:-}
[ -n "$target" ] || { sed -n '2,12p' "$0"; exit 2; }
shift
restore=""
host_ip=""
insecure=0

case "$target" in
  local)
    API_URL=https://localhost:8443 WEB_ORIGIN=https://localhost insecure=1
    dcp() { docker compose -f "$ROOT/docker-compose.prod.yml" -f "$ROOT/docker-compose.prod.local.yml" --env-file "$ROOT/.env.prod" "$@"; }
    echo "== raising the API's per-IP limits for the run (docker-compose.loadtest.yml)"
    dcp -f "$ROOT/docker-compose.loadtest.yml" up -d --no-build --no-deps --wait api
    restore="local"
    # k6 runs in a container: "localhost" must reach this machine's Caddy (same certificate name, so same host name).
    host_ip=$(docker run --rm --add-host gw:host-gateway alpine:3.20 getent hosts gw | awk '{print $1}')
    ;;
  staging)
    : "${STAGING_SSH:?set STAGING_SSH=deploy@<staging server> (the deploy user; docs/server-setup.md)}"
    API_URL=https://${STAGING_API_DOMAIN:-api.staging.instantmechanic.online}
    WEB_ORIGIN=https://${STAGING_WEB_DOMAIN:-diagnose.staging.instantmechanic.online}
    remote='sh "/opt/autocare/releases/$(cat /opt/autocare/shared/current)/scripts/deploy/remote-deploy.sh"'
    echo "== raising staging's per-IP limits for the run"
    ssh "$STAGING_SSH" "$remote limits loadtest"
    restore="staging"
    ;;
  http*://*)
    API_URL=$target WEB_ORIGIN=${1:?give the web origin too: scripts/loadtest.sh <api url> <web origin>}
    shift
    ;;
  *) echo "unknown target $target (staging, local or an https URL)" >&2; exit 2 ;;
esac

VUS=${1:-200}
DURATION=${2:-5m}
cleanup() {
  case "$restore" in
    local) echo "== restoring the local API's limits"; dcp up -d --no-build --no-deps api >/dev/null ;;
    staging) echo "== restoring staging's limits"; ssh "$STAGING_SSH" "$remote limits normal" ;;
  esac
}
trap cleanup EXIT INT TERM

mkdir -p "$ROOT/loadtest/results"
out="loadtest/results/$(echo "$target" | sed 's#https*://##; s#[/:]#_#g')-$(date -u +%Y%m%dT%H%M%SZ).json"
echo "== k6: $VUS concurrent diagnosis sessions for $DURATION against $API_URL"
docker run --rm -i -u "$(id -u):$(id -g)" -v "$ROOT:/work" -w /work \
  -e API_URL="$API_URL" -e WEB_ORIGIN="$WEB_ORIGIN" -e VUS="$VUS" -e DURATION="$DURATION" \
  -e INSECURE="$insecure" -e HOST_IP="$host_ip" -e RAMP="${RAMP:-1m}" \
  "$K6_IMAGE" run --summary-export "$out" loadtest/diagnosis.js
echo "summary: $out"
