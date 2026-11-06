# Rollback

Go back to the previous images. Migrations are the one thing that does not go back by itself.

## 1. Code only (no new migration in the release)
```bash
for i in api web admin; do docker tag autocare-$i:previous autocare-$i:latest; done
git checkout <previous commit>
dcp up -d && dcp ps
```
Check as in [deploy.md](deploy.md) "Check".

## 2. The release added a migration
New migrations add columns or tables; the previous code ignores them, so **usually do step 1 only** and leave the
database as it is (the next deploy uses them again). Only if the new schema breaks the previous code:
```bash
dcp run --rm tools alembic downgrade <previous revision>   # the revision is in the release's README section
```
then step 1. Never downgrade past a migration that deleted or rewrote data: restore instead ([restore.md](restore.md)).

## 3. Data was damaged
Stop writes (`dcp stop api worker`), then [restore.md](restore.md) into a new database and switch to it.

## After
Write down what happened (time, release, symptom, what fixed it) and add a test that would have caught it.
