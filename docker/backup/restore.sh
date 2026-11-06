#!/bin/sh
# Restore one backup into a NEW database, and its photos and pictures into /restore: never over the live data.
#
#   restore.sh <backup> <new database name>
#     <backup>  a folder under /backups (e.g. 2026-11-06T210000Z) or an rclone path (offsite:bucket/2026-11-06T...)
#     needs the age PRIVATE key at $BACKUP_AGE_IDENTITY (default /run/secrets/backup-age.key), mounted only for
#     the restore (docs/runbooks/restore.md), and PGHOST/PGUSER/PGPASSWORD of the server to restore into.
#
# Refuses a database that exists, the live one ($POSTGRES_DB / PGDATABASE) and any *_test database. Checks the
# SHA256SUMS first. Prints the table count and the migration of the restored database to compare.
set -eu
log() { printf '{"time":"%s","service":"restore","level":"%s","message":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"; }
die() { log ERROR "$1"; exit 1; }

[ $# -eq 2 ] || die "usage: restore.sh <backup folder or rclone path> <new database name>"
SRC="$1"; TARGET="$2"
KEY="${BACKUP_AGE_IDENTITY:-/run/secrets/backup-age.key}"
[ -r "$KEY" ] || die "the age private key is not at $KEY (mount it for the restore only)"
echo "$TARGET" | grep -Eq '^[a-z][a-z0-9_]{2,62}$' || die "database name must be lower-case letters, digits, _"
for live in "${POSTGRES_DB:-}" "${PGDATABASE:-}" autocare; do
  [ -n "$live" ] && [ "$TARGET" = "$live" ] && die "refusing to restore into the live database $live: use a new name"
done
case "$TARGET" in *_test) die "refusing a *_test database (pytest uses those)";; esac
EXISTS=$(psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")
[ -z "$EXISTS" ] || die "database $TARGET already exists: restore into a new one"

WORK=$(mktemp -d)
case "$SRC" in
  */*:*|*:*) log INFO "fetching $SRC"; rclone copy "$SRC" "$WORK" --quiet ;;
  *) [ -d "/backups/$SRC" ] || die "no backup /backups/$SRC"; cp -r "/backups/$SRC/." "$WORK/" ;;
esac
(cd "$WORK" && sha256sum -c SHA256SUMS --quiet) || die "checksums do not match: the backup is damaged or incomplete"

log INFO "restoring postgres into $TARGET"
createdb "$TARGET"
age -d -i "$KEY" "$WORK/postgres.dump.age" | pg_restore --no-owner --no-acl --exit-on-error -d "$TARGET"
TABLES=$(psql -d "$TARGET" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
MIGRATION=$(psql -d "$TARGET" -tAc "SELECT version_num FROM alembic_version")
log INFO "restored $TARGET: $TABLES tables, migration $MIGRATION (backup said $(cat "$WORK/MIGRATION" 2>/dev/null || echo ?))"

OUT="/restore/$(basename "$SRC")"
mkdir -p "$OUT"
for part in photos media; do
  if [ -f "$WORK/$part.tar.age" ]; then
    age -d -i "$KEY" "$WORK/$part.tar.age" | tar -C "$OUT" -xf -
    log INFO "$part: $(find "$OUT/$part" -type f | wc -l | tr -d ' ') files in $OUT/$part (copy them back by hand, see the runbook)"
  fi
done
rm -rf "$WORK"
log INFO "restore done: database $TARGET, files in $OUT"
