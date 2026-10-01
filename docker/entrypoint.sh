#!/bin/sh
# LocalDrop container entrypoint.
#
#   1. Wait for PostgreSQL to accept connections.
#   2. Optionally pg_dump the database before migrating
#      (LOCALDROP_BACKUP_BEFORE_MIGRATE=1, compose default).
#   3. apply migrations (forward-only, via the packaged Alembic environment)
#   4. exec uvicorn (tini stays PID 1)
#
# The server refuses to boot without LOCALDROP_SECRET_KEY (>= 32 chars)
# unless LOCALDROP_DEV_MODE=true (never in production images).

set -e

DATA_DIR="${LOCALDROP_DATA_DIR:-/data}"
PORT="${LOCALDROP_PORT:-8080}"

echo "localdrop: data dir is $DATA_DIR"
if [ ! -w "$DATA_DIR" ]; then
  echo "localdrop FATAL: $DATA_DIR is not writable (bind mount? chown it to uid 1000)." >&2
  exit 1
fi

echo "localdrop: waiting for database..."
python - <<'EOF'
import os, sys, time, urllib.parse

url = os.environ.get("LOCALDROP_DATABASE_URL", "")
if not url.startswith("postgresql"):
    print("localdrop FATAL: LOCALDROP_DATABASE_URL must be a postgresql URL", flush=True)
    sys.exit(1)
parsed = urllib.parse.urlparse(url.replace("+psycopg", ""))
host, port = (parsed.hostname or "postgres"), (parsed.port or 5432)
import socket
for i in range(60):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f"localdrop: database reachable at {host}:{port}", flush=True)
        break
    except OSError:
        if i == 59:
            print("localdrop FATAL: database unreachable after 120s", flush=True)
            sys.exit(1)
        time.sleep(2)
EOF

if [ "${LOCALDROP_BACKUP_BEFORE_MIGRATE:-0}" = "1" ]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  DEST="$DATA_DIR/backups/pre-migrate-$STAMP.sql.gz"
  mkdir -p "$DATA_DIR/backups"
  echo "localdrop: pre-migration backup -> $DEST"
  python - <<EOF
import gzip, os, shutil, subprocess, sys, urllib.parse
url = os.environ["LOCALDROP_DATABASE_URL"].replace("+psycopg", "")
p = urllib.parse.urlparse(url)
env = dict(os.environ, PGPASSWORD=urllib.parse.unquote(p.password or ""))
cmd = ["pg_dump", "-h", p.hostname or "postgres", "-p", str(p.port or 5432),
       "-U", urllib.parse.unquote(p.username or "localdrop"), "-d", (p.path or "/localdrop").lstrip("/")]
try:
    with gzip.open("$DEST", "wb") as f:
        subprocess.run(cmd, env=env, stdout=f, stderr=sys.stderr, check=True, timeout=600)
    print("localdrop: backup complete", flush=True)
except Exception as e:
    print(f"localdrop FATAL: pre-migration backup failed: {e}", flush=True)
    sys.exit(1)
EOF
fi

echo "localdrop: applying migrations..."
# `python -m localdrop.migrate` rather than `alembic upgrade head`: the
# migrations ship inside the package, so this works regardless of WORKDIR and
# without a CWD-relative alembic.ini.
python -m localdrop.migrate head

echo "localdrop: starting server on :$PORT"
exec python -m uvicorn localdrop.main:create_app \
  --factory \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --timeout-keep-alive 65 \
  --no-access-log
