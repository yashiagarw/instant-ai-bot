#!/bin/sh
# Dependency and container scanning (Phase 5.4). Part of `pnpm test:all`; also on its own: pnpm test:security
#
#   Python   uv audit (OSV) over backend/uv.lock          fails on any known vulnerability (none ignored today)
#   Node     pnpm audit over pnpm-lock.yaml               fails on high / critical; low and moderate are listed
#   Images   Trivy over the built production images       fails on high / critical that HAVE a fix; unfixed and
#            (autocare-api, -web, -admin, -backup)        lower ones are listed (.trivyignore: accepted ones)
#
# Images are scanned when they exist locally (build them first: README "Phase 5.1"); a missing image or no Docker is
# reported, not failed, so the scan runs on a laptop without the stack. SCAN_IMAGES=0 skips them.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
FAILED=0
step() { printf '\n== %s\n' "$1"; }

step "Python dependencies (uv audit)"
if (cd "$ROOT/backend" && uv audit --frozen --preview-features audit-command); then :; else FAILED=1; fi

step "Node dependencies (pnpm audit, failing on high and critical)"
(cd "$ROOT" && pnpm audit --audit-level low >/dev/null 2>&1) || (cd "$ROOT" && pnpm audit 2>/dev/null | tail -3)
if (cd "$ROOT" && pnpm audit --audit-level high >/dev/null 2>&1); then echo "no high or critical advisories"; else
  (cd "$ROOT" && pnpm audit --audit-level high); FAILED=1
fi

if [ "${SCAN_IMAGES:-1}" != "0" ]; then
  step "Container images (Trivy: high and critical with a fix)"
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running: images not scanned"
  else
    for image in autocare-api:latest autocare-web:latest autocare-admin:latest autocare-backup:latest; do
      if ! docker image inspect "$image" >/dev/null 2>&1; then echo "$image: not built here, skipped"; continue; fi
      echo "-- $image"
      if ! docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/trivy \
          -v "$ROOT/.trivyignore:/.trivyignore:ro" aquasec/trivy:0.67.2 image --quiet --scanners vuln \
          --ignorefile /.trivyignore --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$image"; then
        FAILED=1
      fi
    done
  fi
fi

[ $FAILED -eq 0 ] && printf '\nSecurity scan passed.\n' || printf '\nSecurity scan FAILED (see above).\n'
exit $FAILED
