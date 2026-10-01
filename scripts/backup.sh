#!/usr/bin/env bash
# LocalDrop backup: database dump + file storage, timestamped.
#
# Usage: ./scripts/backup.sh [destination-dir]   (default: ./backups)
#
# Captures the three things a restore needs:
#   1. PostgreSQL dump  (localdrop-db-<ts>.sql.gz)
#   2. File storage     (localdrop-data-<ts>.tar.gz, from the appdata volume)
#   3. Your .env        (localdrop-env-<ts>.txt — secrets outside the DB)
#
# Requires: docker compose stack running (or at least the `postgres` service).
set -euo pipefail
cd "$(dirname "$0")/.."

DEST="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

echo "==> database dump..."
docker compose exec -T postgres pg_dump -U localdrop -d localdrop \
  | gzip > "$DEST/localdrop-db-$STAMP.sql.gz"

echo "==> file storage archive..."
docker run --rm \
  -v localdrop-appdata:/data:ro \
  -v "$PWD/$DEST:/out" \
  alpine tar -czf "/out/localdrop-data-$STAMP.tar.gz" -C /data .

echo "==> environment snapshot..."
cp .env "$DEST/localdrop-env-$STAMP.txt" 2>/dev/null || echo "(no .env file — skipped)"

ls -la "$DEST"/*"$STAMP"*
echo "backup complete: $DEST (keep all three files together)"
