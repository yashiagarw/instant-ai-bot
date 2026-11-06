#!/bin/sh
# Backup-and-restore test (Phase 5.4, docs/runbooks/restore.md). Run it against the running production stack
# (locally: README "Phase 5.1"), after building the backup image (dcp build backup).
#
#   sh scripts/backup_restore_test.sh
#
# 1. Makes a throwaway age key pair (test only; real backups use the key kept off the server).
# 2. Runs backup.sh once into a temporary folder (not the backups volume): Postgres, the photo bucket, data/media.
# 3. Starts a THROWAWAY Postgres (pgvector) container on its own network, with no ports: the restore never goes near
#    the development database or the production stack's database.
# 4. Runs restore.sh into a new database there, then compares the row count of every table, the migration and the
#    photo / picture counts with the source. Also checks that restore.sh refuses the live database's name.
# 5. Removes the throwaway container, network, key and files.
#
# COMPOSE (default: the local production test) chooses the stack:
#   COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod" sh scripts/backup_restore_test.sh
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
P=${COMPOSE:-"docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml --env-file .env.prod --profile storage"}
IMAGE=${BACKUP_IMAGE:-autocare-backup:latest}
NAME="im-restore-test-$$"
WORK=$(mktemp -d)
PW=$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 24)
ok() { printf 'OK    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; exit 1; }
cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker network rm "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "build the backup image first ($P build backup)"
mkdir -p "$WORK/backups" "$WORK/restore"
chmod 777 "$WORK/backups" "$WORK/restore"

# 1. throwaway key
docker run --rm --entrypoint age-keygen "$IMAGE" > "$WORK/key.txt" 2>/dev/null
chmod 644 "$WORK/key.txt"
RECIPIENT=$(sed -n 's/^# public key: //p' "$WORK/key.txt")
[ -n "$RECIPIENT" ] && ok "throwaway age key pair"

# 2. one backup into the temporary folder
$P run --rm -T -e BACKUP_AGE_RECIPIENT="$RECIPIENT" -e BACKUP_REMOTE= -v "$WORK/backups:/backups" backup backup.sh
STAMP=$(ls "$WORK/backups")
[ -f "$WORK/backups/$STAMP/postgres.dump.age" ] || fail "no database backup written"
if head -c 64 "$WORK/backups/$STAMP/postgres.dump.age" | grep -q "PGDMP"; then fail "the dump is not encrypted"; fi
grep -q "age-encryption.org" "$WORK/backups/$STAMP/postgres.dump.age" && ok "backup $STAMP written and encrypted ($(du -sh "$WORK/backups/$STAMP" | cut -f1))"

# 3. a throwaway Postgres, own network, no ports
docker network create "$NAME" >/dev/null
docker run -d --name "$NAME" --network "$NAME" -e POSTGRES_PASSWORD="$PW" pgvector/pgvector:pg16 >/dev/null
for _ in $(seq 1 60); do docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
docker exec "$NAME" pg_isready -U postgres >/dev/null || fail "throwaway Postgres did not start"
ok "throwaway Postgres $NAME (no ports, own network)"

run_restore() {
  docker run --rm --network "$NAME" -e PGHOST="$NAME" -e PGUSER=postgres -e PGPASSWORD="$PW" -e PGDATABASE=postgres \
    -e POSTGRES_DB=autocare -v "$WORK/backups:/backups:ro" -v "$WORK/key.txt:/run/secrets/backup-age.key:ro" \
    -v "$WORK/restore:/restore" "$IMAGE" restore.sh "$STAMP" "$1"
}

# 4a. refuses the live database's name
if run_restore autocare >/dev/null 2>&1; then fail "restore.sh accepted the live database name"; fi
ok "restore refuses the live database name"

# 4b. restore and compare
run_restore restore_check
COUNTS="SELECT table_name || '=' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I', table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
$P exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"$COUNTS\"" > "$WORK/source.txt"
docker exec "$NAME" psql -U postgres -d restore_check -tAc "$COUNTS" > "$WORK/restored.txt"
if diff "$WORK/source.txt" "$WORK/restored.txt" >/dev/null; then
  ok "all $(wc -l < "$WORK/source.txt" | tr -d ' ') tables have the same row counts ($(awk -F= '{s+=$2} END {print s}' "$WORK/source.txt") rows)"
else
  diff "$WORK/source.txt" "$WORK/restored.txt" | head -20
  fail "row counts differ (rows written while the backup ran show up here: run it on a quiet stack)"
fi
SRC_MIG=$($P exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '\r')
DST_MIG=$(docker exec "$NAME" psql -U postgres -d restore_check -tAc "SELECT version_num FROM alembic_version")
[ "$SRC_MIG" = "$DST_MIG" ] && ok "migration $DST_MIG" || fail "migration $DST_MIG, source $SRC_MIG"
for part in photos media; do
  want=$(cat "$WORK/backups/$STAMP/$(echo $part | tr a-z A-Z)" 2>/dev/null || echo "")
  [ -z "$want" ] && { printf 'SKIP  %s not in this backup\n' "$part"; continue; }
  got=$(find "$WORK/restore/$STAMP/$part" -type f 2>/dev/null | wc -l | tr -d ' ')
  [ "$got" = "$want" ] && ok "$part: $got files restored" || fail "$part: $got files restored, $want backed up"
done
printf '\nBackup and restore test passed (throwaway database and files removed).\n'
