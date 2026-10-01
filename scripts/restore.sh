#!/usr/bin/env bash
# LocalDrop restore: rebuild database + storage from a backup.sh set.
#
# Usage: ./scripts/restore.sh <timestamp> [backup-dir]   (default dir: ./backups)
#   Example: ./scripts/restore.sh 20260101T120000Z
#
# WARNING: this REPLACES the current database and file storage.
# The stack is stopped first; start it again with `docker compose up -d`.
#
# Constraints (see BACKUP.md):
#   - restore onto the SAME LocalDrop version that made the backup,
#   - keep LOCALDROP_DATA_DIR=/data (the container path must not change).
set -euo pipefail
cd "$(dirname "$0")/.."

TS="${1:?usage: restore.sh <timestamp> [backup-dir]}"
SRC="${2:-./backups}"
for f in "$SRC/localdrop-db-$TS.sql.gz" "$SRC/localdrop-data-$TS.tar.gz"; do
  [ -f "$f" ] || { echo "missing: $f" >&2; exit 1; }
done

echo "==> stopping stack..."
docker compose down

echo "==> clearing volumes (fresh pgdata + appdata)..."
docker volume rm -f localdrop-pgdata localdrop-appdata >/dev/null
docker volume create localdrop-appdata >/dev/null
docker volume create localdrop-pgdata >/dev/null

echo "==> restoring file storage..."
docker run --rm \
  -v localdrop-appdata:/data \
  -v "$PWD/$SRC:/in:ro" \
  alpine tar -xzf "/in/localdrop-data-$TS.tar.gz" -C /data

echo "==> starting postgres only..."
docker compose up -d postgres
sleep 8

echo "==> restoring database..."
gunzip -c "$SRC/localdrop-db-$TS.sql.gz" \
  | docker compose exec -T postgres psql -U localdrop -d localdrop -v ON_ERROR_STOP=1 -q

echo "==> restore complete. Start the stack:  docker compose up -d"
echo "    Then verify: open the UI, log in, download a file."
