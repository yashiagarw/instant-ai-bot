# Deploy

Releases are commits on `main`. Since Phase 5.6 GitHub Actions deploys them (`.github/workflows/main.yml`); this page
says what it does, what to watch, and how to do it by hand when Actions is down. Deploy outside 18:00-22:00 India
time (busiest); budget 15 minutes.

## The pipeline (normal path)
1. A pull request passes its checks (CI: lint, types, tests, dependency audit, the eval gate). Merge it.
2. On `main`: the same checks, Playwright, the images (`ghcr.io/<owner>/autocare-api:<sha>` …), Trivy.
3. **Staging**: web/admin built for staging, the release shipped, `remote-deploy.sh deploy <sha>` (migrations run
   first; it waits until every service is healthy), then the smoke test (including starting a diagnosis).
4. **Production waits for your approval** (Actions > the run > "Review deployments"). Before approving, read the
   commit's README section for "after pulling" steps (new settings go into `/opt/autocare/shared/*.env.prod` first)
   and open staging once.
5. Production: a fresh encrypted backup (`PRE_DEPLOY_BACKUP=1`), the deploy, the smoke test. **If the smoke test
   fails, it rolls back to the previous release by itself** (images only; the database is never downgraded) and the
   run fails red: then follow [rollback.md](rollback.md) "After".

## Check (5 minutes, after a production deploy)
- The run's summary shows the release (`remote-deploy.sh status`) and a passed smoke test.
- `curl -s https://api.instantmechanic.online/api/health/ready` → `"status":"ok"` and `"migrations":"ok"`.
- Open the website, start a diagnosis, see a question. Open the admin app and the request queue.
- Sentry shows no new issues; the uptime monitor is green.

If anything is wrong and not fixable in 10 minutes: [rollback.md](rollback.md).

## By hand (Actions unavailable)
Any commit that went through `main` has its images in GHCR. From your laptop, as the deploy user:
```bash
sha=<full commit sha>
ssh deploy@<server> "mkdir -p /opt/autocare/releases/$sha"
git archive "$sha" docker-compose.prod.yml docker-compose.loadtest.yml docker/caddy docker/backup scripts/deploy \
  | ssh deploy@<server> "tar -xf - -C /opt/autocare/releases/$sha"
ssh deploy@<server> "sh /opt/autocare/releases/$sha/scripts/deploy/remote-deploy.sh deploy $sha"
sh scripts/deploy/smoke.sh diagnose.instantmechanic.online api.instantmechanic.online admin.instantmechanic.online
```
The web/admin images of that environment must exist (`autocare-web:production-<sha>`): they do for every commit that
reached production through the pipeline; otherwise use Actions > "Deploy (manual)", which builds them.

Without GHCR at all (registry down): build on the server as before Phase 5.6 (README "Phase 5.1", `dcp build ...`),
one image at a time.
