#!/bin/sh
# Smoke test of a deployed environment from outside (Phase 5.6): HTTPS on every host, the API ready with its
# migrations, the website and admin app serving with their security headers, and the API answering real reads.
# Used by GitHub Actions after every staging and production deploy (a failure on production rolls back).
#
#   sh scripts/deploy/smoke.sh <web domain> <api domain> <admin domain> [--write]
#   e.g. sh scripts/deploy/smoke.sh diagnose.instantmechanic.online api.instantmechanic.online admin.instantmechanic.online
#
# --write (staging only) also starts a diagnosis and loads its first question: it creates a session, so never on
# production. Retries for up to SMOKE_WAIT seconds (default 120) while certificates and containers settle.
set -u
WEB=$1 API=$2 ADMIN=$3 WRITE=${4:-}
WAIT=${SMOKE_WAIT:-120}
FAILED=0
# SMOKE_INSECURE=1: the local production stack only (Caddy's own certificate, no port-80 redirect test).
CURL="curl -sS --max-time 15 --retry 2 --retry-all-errors ${SMOKE_INSECURE:+-k}"

check() {  # name, then a command that must succeed
  name=$1; shift
  if "$@"; then printf 'ok    %s\n' "$name"; else printf 'FAIL  %s\n' "$name"; FAILED=1; fi
}

# Wait for the API to answer ready (a fresh deploy may still be starting behind Caddy).
waited=0
until $CURL -f "https://$API/api/health/ready" >/dev/null 2>&1; do
  [ "$waited" -ge "$WAIT" ] && break
  sleep 5; waited=$((waited + 5))
done

ready() { $CURL "https://$API/api/health/ready" | grep -q '"database":"ok"' && $CURL "https://$API/api/health/ready" | grep -Eq '"migrations":"(ok|ahead)"'; }
status200() { [ "$($CURL -o /dev/null -w '%{http_code}' "$1")" = 200 ]; }
has() { $CURL "$1" | grep -q "$2"; }
header() { $CURL -o /dev/null -D - "$1" | tr -d '\r' | grep -qi "^$2"; }
http_redirects() { $CURL -o /dev/null -w '%{http_code}' "http://$1/" | grep -Eq '^30[178]$'; }

check "API ready, migrations applied"           ready
check "API categories"                          has "https://$API/api/categories" '"topics"'
check "API vehicle search"                      has "https://$API/api/vehicles/search?q=swift&limit=1" '"results"'
check "website home page"                       has "https://$WEB/" 'Instant'
check "website /hi page"                        status200 "https://$WEB/hi"
check "website /diagnose"                       status200 "https://$WEB/diagnose"
check "website health"                          status200 "https://$WEB/healthz"
check "website CSP header"                      header "https://$WEB/" "content-security-policy:"
check "website HSTS header"                     header "https://$WEB/" "strict-transport-security:"
check "service worker not cached"               header "https://$WEB/sw.js" "cache-control: no-cache, no-store"
check "admin sign-in page"                      status200 "https://$ADMIN/login"
check "admin CSP header"                        header "https://$ADMIN/login" "content-security-policy:"
[ -n "${SMOKE_INSECURE:-}" ] || check "http redirects to https" http_redirects "$WEB"

if [ "$WRITE" = "--write" ]; then
  start() {
    variant=$($CURL "https://$API/api/vehicles/search?q=swift&limit=1" | sed -n 's/.*"variant_id":\([0-9]*\).*/\1/p' | head -1)
    if [ -z "$variant" ]; then
      echo "      (no vehicles yet: a new server before its data is loaded, docs/server-setup.md step 10)"; return 0
    fi
    $CURL -f -X POST "https://$API/api/diagnosis/sessions" -H 'Content-Type: application/json' -H "Origin: https://$WEB" \
      -d "{\"vehicle\":{\"variant_id\":$variant},\"category_ids\":[\"battery\"],\"text\":\"smoke test: battery weak\"}" \
      | grep -Eq '"(question|done)"'
  }
  check "diagnosis starts (staging only)"      start
fi

[ $FAILED -eq 0 ] && echo "Smoke test passed: $WEB" || echo "Smoke test FAILED: $WEB"
exit $FAILED
