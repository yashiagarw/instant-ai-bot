# Rollback

Go back to the previous release's images. Migrations are the one thing that does not go back by itself: **a rollback
never downgrades the database automatically**.

## 0. What happens by itself
When production's smoke test fails after a deploy, the pipeline runs `remote-deploy.sh rollback`: the previous
release's images and compose file, started **without** the `migrate` step, then the smoke test again. The run ends red
either way. The previous code ignores columns and tables added by a newer migration, so the API serves; its readiness
reports `"migrations":"ahead"` (still 200) until the next deploy.

## 1. Code only (the usual case)
Actions > "Deploy (manual)" > environment, action **rollback** (production asks for approval). Or on the server:
```bash
sh /opt/autocare/releases/$(cat /opt/autocare/shared/current)/scripts/deploy/remote-deploy.sh rollback
sh /opt/autocare/releases/$(cat /opt/autocare/shared/current)/scripts/deploy/remote-deploy.sh status
```
`rollback` goes back exactly one release and then forgets "previous" (no ping-pong). To go back further, deploy an
older commit by its sha: Actions > "Deploy (manual)" > deploy (every image tag is kept in GHCR), or
[deploy.md](deploy.md) "By hand". Check as in [deploy.md](deploy.md) "Check".

## 2. The release added a migration
**Usually do step 1 only** and leave the database as it is (the next deploy uses the new columns again). Only if the
new schema breaks the previous code, by hand, after reading the migration:
```bash
cd /opt/autocare/releases/<the NEWER release's sha>     # its code knows the migration it is undoing
dcp() { docker compose -p autocare-prod --project-directory . -f docker-compose.prod.yml --env-file /opt/autocare/shared/.env.prod "$@"; }
API_IMAGE=<image repo>/autocare-api:<newer sha> dcp run --rm tools alembic downgrade <previous revision>
```
then step 1. The previous revision is in the release's README section. Never downgrade past a migration that deleted
or rewrote data: restore instead ([restore.md](restore.md)). Production took a backup just before the deploy
(`PRE_DEPLOY_BACKUP=1`).

## 3. Data was damaged
Stop writes (`dcp stop api worker`), then [restore.md](restore.md) into a new database and switch to it.

## After
Write down what happened (time, release, symptom, what fixed it) and add a test that would have caught it. Rehearse
the rollback on staging after any change to the pipeline or to `scripts/deploy/`.
