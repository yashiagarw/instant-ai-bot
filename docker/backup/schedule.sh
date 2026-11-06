#!/bin/sh
# Runs backup.sh every day at BACKUP_AT (UTC, HH:MM; default 21:00 = 02:30 India time), forever.
set -eu
AT="${BACKUP_AT:-21:00}"
echo "{\"service\":\"backup\",\"level\":\"INFO\",\"message\":\"daily backups at $AT UTC\"}"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "today $AT" +%s)
  [ "$next" -le "$now" ] && next=$(date -u -d "tomorrow $AT" +%s)
  sleep $((next - now))
  backup.sh || echo "{\"service\":\"backup\",\"level\":\"ERROR\",\"message\":\"backup failed (see above); next try tomorrow\"}"
done
