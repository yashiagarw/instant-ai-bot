#!/bin/sh
# OWASP ZAP baseline scan (passive: spiders and inspects responses, no attacks) against the local production stack
# (README "Phase 5.4"). ZAP runs inside Caddy's network namespace, so https://localhost, :8443 (API) and :8444
# (admin) reach Caddy with the same host names as a browser. Reports: zap-reports/<target>.html / .md (git-ignored).
#
#   sh scripts/zap-baseline.sh            # web, API, admin
#   ZAP_MINUTES=1 sh scripts/zap-baseline.sh
#
# Exit 1 if any target has a FAIL; warnings (ZAP's "WARN-NEW") are listed for review, see scripts/zap-rules.tsv.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
P=${COMPOSE:-"docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml --env-file .env.prod --profile storage"}
CADDY=$(cd "$ROOT" && $P ps -q caddy)
[ -n "$CADDY" ] || { echo "Start the production stack first (README 'Phase 5.4')"; exit 1; }
OUT="$ROOT/zap-reports"
mkdir -p "$OUT" && chmod 777 "$OUT"
# Locally Caddy sends HSTS max-age=0 (HSTS_MAX_AGE, so browsers do not pin https on localhost): that one rule is
# INFO for localhost targets only; against a real domain it stays FAIL.
sed 's/^10035\tFAIL/10035\tINFO/' "$ROOT/scripts/zap-rules.tsv" > "$OUT/rules.tsv"
FAILED=0
for target in web=https://localhost/ api=https://localhost:8443/api/health admin=https://localhost:8444/login; do
  name=${target%%=*}; url=${target#*=}
  echo "== ZAP baseline: $name ($url)"
  docker run --rm --network "container:$CADDY" -v "$OUT:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:stable \
    zap-baseline.py -t "$url" -m "${ZAP_MINUTES:-2}" -c rules.tsv -r "$name.html" -w "$name.md" -I -s \
    | grep -E "^(FAIL|WARN|PASS: |INFO)|^FAIL-NEW|^WARN-NEW" | grep -v "^PASS" || true
  if grep -q "^FAIL" "$OUT/$name.md" 2>/dev/null || grep -qE "FAIL-NEW: [1-9]" "$OUT/$name.md" 2>/dev/null; then FAILED=1; fi
done
echo "Reports: $OUT"
exit $FAILED
