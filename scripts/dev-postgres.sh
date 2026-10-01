#!/usr/bin/env bash
# Local dev Postgres helper (Windows host, no Docker required).
#
# LocalDrop development on this machine uses an embedded PostgreSQL 16.4
# (Zonky binaries) at C:\Users\Public\localdrop-pg, running on port 5433.
# Production deployments use the Docker Compose stack instead (docker/).
#
# Usage:
#   ./scripts/dev-postgres.sh start|stop|status
set -euo pipefail
ROOT="C:\\Users\\Public\\localdrop-pg"
PSQL="$ROOT\\app\\bin\\psql.exe"

start() {
  # schtasks runs pg_ctl with the user's non-elevated token (postgres.exe
  # refuses to run as Administrator).
  schtasks //create //tn "localdrop-pg" //tr "\"$ROOT\\app\\bin\\pg_ctl.exe\" -D \"$ROOT\\data\" -o \"-p 5433\" -l \"$ROOT\\pg.log\" start" //sc once //st 00:00 //f
  schtasks //run //tn "localdrop-pg"
  sleep 4
  "$PSQL" -h 127.0.0.1 -p 5433 -U postgres -d localdrop -c "SELECT 1;" >/dev/null && echo "postgres: up on 5433"
}

stop() {
  "$ROOT\\app\\bin\\pg_ctl.exe" -D "$ROOT\\data" -m fast stop || true
}

status() {
  "$PSQL" -h 127.0.0.1 -p 5433 -U postgres -d localdrop -c "SELECT version();" 2>/dev/null | head -3 || echo "postgres: down"
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  *) status ;;
esac
