# Backup & restore

A complete backup is three things, kept together:

1. **Database dump** — users, sessions, file/folder metadata, shares.
2. **File storage** — the actual bytes (`appdata` volume).
3. **Your `.env`** — secrets and config (not in the database).

Lose any one of them and the restore is incomplete (metadata without bytes,
or bytes without names).

## Back up

```bash
./scripts/backup.sh            # -> ./backups/
./scripts/backup.sh /mnt/nas/localdrop-backups
```

Each run writes three timestamped files, e.g.
`localdrop-db-20260101T120000Z.sql.gz`,
`localdrop-data-20260101T120000Z.tar.gz`, `localdrop-env-20260101T120000Z.txt`.
Automate with cron (daily is plenty for a home server):

```cron
0 3 * * * cd /opt/localdrop && ./scripts/backup.sh /mnt/nas/localdrop-backups >> /var/log/localdrop-backup.log 2>&1
```

Additionally, every container upgrade auto-dumps the database to
`/data/backups/pre-migrate-<ts>.sql.gz` *inside* the data volume
(`LOCALDROP_BACKUP_BEFORE_MIGRATE=1` in compose) — a safety net, not a backup
strategy (it lives on the same disk).

## Restore

```bash
./scripts/restore.sh 20260101T120000Z
./scripts/restore.sh 20260101T120000Z /mnt/nas/localdrop-backups
docker compose up -d
```

Then verify: log in, open a folder, download a file and compare it.

> **Rules:** restore onto the **same LocalDrop version** that made the backup,
> and keep the container data path `/data` unchanged (database rows reference
> absolute paths under it — see CONFIGURATION.md).

## Disaster drill (do this once)

1. `docker compose down -v` on a **spare** machine (never your live data).
2. Copy one backup set over, `restore.sh`, `up -d`.
3. Log in, download two files, open a share link.
4. If anything fails, you found out on a spare machine — fix the backup first.

## What is NOT backed up

- Interrupted uploads (`.part` staging files) — re-upload them.
- Container logs, Prometheus metrics, thumbnails (regenerated on demand).
