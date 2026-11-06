#!/bin/sh
# One encrypted backup: Postgres (custom-format dump), the customer photo bucket, and data/media (fault pictures).
#
#   docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm backup backup.sh     # now, by hand
#
# Each part is encrypted with age to BACKUP_AGE_RECIPIENT (a public key, "age1..."): the server can write backups
# but cannot read them. The private key is kept OFF the server (docs/runbooks/restore.md). Without a recipient
# nothing is written (never unencrypted). Written to /backups/<UTC time>/ with SHA256SUMS, then copied to
# BACKUP_REMOTE (an rclone remote, e.g. offsite:instant-mechanic-backups) when it is set; backups older than
# BACKUP_RETENTION_DAYS (30) are deleted in both places.
#
# Needs: PGHOST/PGUSER/PGPASSWORD/PGDATABASE (compose sets them); for the photos S3_ENDPOINT_URL, S3_ACCESS_KEY,
# S3_SECRET_KEY, S3_BUCKET (from backend/.env.prod); for the off-site copy RCLONE_CONFIG_OFFSITE_* (see
# .env.prod.example). data/media is mounted read-only at /data/media.
set -eu
log() { printf '{"time":"%s","service":"backup","level":"%s","message":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"; }

if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
  log WARNING "BACKUP_AGE_RECIPIENT is not set: backups are off (they are never written unencrypted)"
  exit 0
fi
RETENTION="${BACKUP_RETENTION_DAYS:-30}"
STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
DIR="/backups/$STAMP"
mkdir -p "$DIR"
enc() { age -r "$BACKUP_AGE_RECIPIENT" -o "$1"; }

log INFO "backup $STAMP: postgres"
pg_dump --format=custom --no-owner --no-acl | enc "$DIR/postgres.dump.age"
psql -tAc "SELECT version_num FROM alembic_version" > "$DIR/MIGRATION" 2>/dev/null || echo unknown > "$DIR/MIGRATION"

if [ -n "${S3_ENDPOINT_URL:-}" ] && [ -n "${S3_ACCESS_KEY:-}" ] && [ -n "${S3_BUCKET:-}" ]; then
  log INFO "backup $STAMP: photos (bucket $S3_BUCKET)"
  TMP=$(mktemp -d)
  RCLONE_CONFIG_PHOTOS_TYPE=s3 RCLONE_CONFIG_PHOTOS_PROVIDER=Other RCLONE_CONFIG_PHOTOS_ENDPOINT="$S3_ENDPOINT_URL" \
  RCLONE_CONFIG_PHOTOS_ACCESS_KEY_ID="$S3_ACCESS_KEY" RCLONE_CONFIG_PHOTOS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
  RCLONE_CONFIG_PHOTOS_REGION="${S3_REGION:-us-east-1}" \
    rclone copy "photos:$S3_BUCKET" "$TMP/photos" --quiet
  tar -C "$TMP" -cf - photos | enc "$DIR/photos.tar.age"
  find "$TMP/photos" -type f | wc -l | tr -d ' ' > "$DIR/PHOTOS"
  rm -rf "$TMP"
else
  log WARNING "photo storage not configured (S3_*): photos not backed up"
fi

if [ -d /data/media ]; then
  log INFO "backup $STAMP: data/media"
  tar -C /data -cf - media | enc "$DIR/media.tar.age"
  find /data/media -type f | wc -l | tr -d ' ' > "$DIR/MEDIA"
fi

(cd "$DIR" && sha256sum ./*.age > SHA256SUMS)
log INFO "backup $STAMP written ($(du -sh "$DIR" | cut -f1))"

if [ -n "${BACKUP_REMOTE:-}" ]; then
  rclone copy "$DIR" "$BACKUP_REMOTE/$STAMP" --quiet
  rclone delete "$BACKUP_REMOTE" --min-age "${RETENTION}d" --quiet || true
  rclone rmdirs "$BACKUP_REMOTE" --leave-root --quiet || true
  log INFO "backup $STAMP copied to the off-site store; older than $RETENTION days removed there"
else
  log WARNING "BACKUP_REMOTE is not set: the backup is only on this server (set up off-site storage)"
fi
find /backups -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION" -exec rm -rf {} +
log INFO "backup $STAMP done"
