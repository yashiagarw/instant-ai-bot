# Deploy

Releases are git commits on `main`, deployed by hand. Budget 15 minutes; deploy outside 18:00-22:00 India time (busiest).

## Before
1. Tests are green on the commit: `pnpm test:all` (backend, frontend, dependency and image scans) and the Playwright
   suites (README "Phase 5.4").
2. Read the commit's README section for "after pulling" steps (new settings, one-off commands).
3. Note the running version, for a rollback: `git rev-parse --short HEAD` on the server, and tag the images:
   ```bash
   for i in api web admin; do docker tag autocare-$i:latest autocare-$i:previous; done
   ```
4. Recent backup exists: `dcp exec backup ls /backups | tail -1` (today's or yesterday's). If not, run one now:
   `dcp run --rm backup backup.sh`.

## Deploy
```bash
git fetch && git checkout <commit> && git log -1 --oneline
# new settings? add them to .env.prod / backend/.env.prod (compare with the .example files)
dcp build api && dcp build web && dcp build admin && dcp build backup   # one at a time on a small server
dcp up -d          # migrate runs first; api and worker start only if it succeeded
dcp ps             # every service healthy, migrate "exited (0)"
```

## Check (5 minutes)
- `curl -s https://api.instantmechanic.online/api/health/ready` → `{"status":"ok", ... "migrations":"ok"}`
- Open the website, start a diagnosis, see a question. Open the admin app and the request queue.
- `dcp logs --since 5m api worker | grep -E '"level": "(ERROR|CRITICAL)"'` is empty; Sentry shows no new issues.
- The uptime monitor is green.

If anything is wrong and not fixable in 10 minutes: [rollback.md](rollback.md).
