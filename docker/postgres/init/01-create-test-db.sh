#!/bin/sh
# Runs once, when the pgdata volume is first created.
# Creates the pytest database next to the main one.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE DATABASE "${POSTGRES_TEST_DB:-autocare_test}" OWNER "$POSTGRES_USER";
SQL
