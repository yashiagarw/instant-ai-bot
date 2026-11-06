# Backups and restore

## What is backed up
Daily at 02:30 India time (`BACKUP_AT`, UTC), by the `backup` service:

| Part | File | Notes |
|---|---|---|
| Postgres (everything) | `postgres.dump.age` | `pg_dump` custom format |
| Customer photos (S3 bucket) | `photos.tar.age` | SeaweedFS or the cloud bucket in `S3_*` |
| Fault pictures | `media.tar.age` | `data/media` (the importer recreates them too) |

Each file is encrypted with [age](https://age-encryption.org) to `BACKUP_AGE_RECIPIENT`, a **public** key: the server
can write backups but not read them. Backups are kept 30 days (`BACKUP_RETENTION_DAYS`) on the server (`backups`
volume) and off-site (`BACKUP_REMOTE`, an S3-compatible bucket, e.g. Cloudflare R2). `SHA256SUMS` checks them.

## The key (once)
On a trusted laptop, not the server:
```bash
age-keygen -o instant-mechanic-backup.key     # prints "Public key: age1..."
```
- Put the **public** key in `.env.prod` as `BACKUP_AGE_RECIPIENT`.
- Keep the **private** key file in the company password manager **and** on an offline copy (USB in a safe). Two
  people must be able to reach it. Without it, no backup can be read.
- Off-site bucket: create it with a 35-day lifecycle rule as a second guard; give the server a key that can write
  and list but not delete other buckets.

## Monthly restore test (and after any backup change)
On the server or locally (it never touches the live database):
```bash
sh scripts/backup_restore_test.sh
```
It backs up once with a throwaway key, restores into a throwaway Postgres container and compares every table's row
count, the migration and the photo / picture counts. Record the date and result here:

| Date | Who | Result |
|---|---|---|
| 2026-11-06 | Phase 5.4, local production stack | passed: 85 tables / 118,564 rows, migration 0024, 2 photos, 731 pictures |

## Real restore
Always into a **new** database; switch only when it checks out.
1. Pick the backup: `dcp exec backup ls /backups` or `rclone lsd offsite:<bucket>/<folder>`.
2. Copy the private key to the server for the restore only: `scp instant-mechanic-backup.key server:/tmp/` .
3. Restore:
   ```bash
   dcp run --rm -v /tmp/instant-mechanic-backup.key:/run/secrets/backup-age.key:ro -v /srv/restore:/restore \
     backup restore.sh <2026-11-06T210000Z or offsite:bucket/folder/2026-11-06T210000Z> autocare_restored
   ```
   It refuses an existing database, the live one and any `*_test` one, checks the checksums, and prints the table
   count and migration. Photos and pictures land in `/srv/restore/<backup>/`.
4. Check: `dcp exec db psql -U autocare -d autocare_restored -c "select count(*) from service_requests"`, and open
   a few recent requests.
5. Switch: `dcp stop api worker`; in Postgres rename `autocare` → `autocare_broken_<date>` and
   `autocare_restored` → `autocare` (`ALTER DATABASE ... RENAME TO ...`, no one connected); `dcp up -d`.
6. Photos: `rclone copy /srv/restore/<backup>/photos photos:<bucket>` (an rclone remote for the bucket), pictures:
   `cp -r /srv/restore/<backup>/media/. data/media/`.
7. Delete `/tmp/instant-mechanic-backup.key` and `/srv/restore`. Keep `autocare_broken_<date>` a week, then drop it.
8. Data since the backup is lost: tell support which requests may need a call (the time window).
