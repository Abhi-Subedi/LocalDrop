# Configuration

Every setting arrives as a `LOCALDROP_*` environment variable (12-factor).
`backend/src/localdrop/config.py` is the single source of truth, and
`scripts/check_config_docs.py` fails CI if this table drifts from it.

**Where to put them**

| Install | Where settings live |
|---|---|
| Docker Compose | `.env` beside `docker-compose.yml`; the compose file passes them into the container |
| Native Linux (systemd) | `/etc/localdrop/localdrop.env`, referenced by the unit's `EnvironmentFile=` |
| Native macOS (launchd) | `~/Library/Application Support/LocalDrop/localdrop.env` |
| Windows | The launcher reads `localdrop.env` from the data dir, and the real environment wins over both |
| From source | Whatever your shell or process manager sets |

## Reference

| Variable | Default | What |
|---|---|---|
| `LOCALDROP_SECRET_KEY` | *(generated)* | HMAC/session secret, **≥ 32 chars**. The server refuses to boot without it unless `LOCALDROP_DEV_MODE` is on. Generated into `secret.key` in the data dir on first run. |
| `LOCALDROP_DATA_DIR` | `/var/lib/localdrop` | File storage root, and the location of the embedded database. Stored paths are relative to it, so a restore to a different path works — keep it stable anyway. Docker uses `/data`. |
| `LOCALDROP_DATABASE_URL` | `postgresql+psycopg://postgres@127.0.0.1:5433/localdrop` | SQLAlchemy URL. **Leave unset on native installs** and LocalDrop starts its own embedded PostgreSQL in the data dir. Docker always sets this. |
| `LOCALDROP_DB_CONNECT_TIMEOUT` | `5` | Seconds to wait for a TCP connect to PostgreSQL. Keep it under your probe timeout: Docker uses 5 s, most orchestrators ~30 s. libpq waits ~2 minutes by default, which is useless for a readiness check. |
| `LOCALDROP_DB_KEEPALIVE_SECONDS` | `30` | Idle seconds before a TCP keepalive probe. Three missed probes close a half-open connection so it cannot pin a pool slot. |
| `LOCALDROP_PORT` | `8080` | Port the server listens on. |
| `LOCALDROP_PUBLIC_URL` | *(empty)* | Public base URL used in share links and the QR code, e.g. `https://files.example.com`. Empty = derive per request from the `Host` header. |
| `LOCALDROP_TRUSTED_PROXIES` | `0` | Number of trusted proxy hops in `X-Forwarded-For`. `0` = take the client IP from the socket (spoof-proof). |
| `LOCALDROP_MAX_UPLOAD_BYTES` | `107374182400` (100 GiB) | Largest single-file upload. Bigger → `413`. `0` = unlimited (not recommended). |
| `LOCALDROP_UPLOAD_CHUNK_MAX_BYTES` | `8388608` (8 MiB) | Largest accepted tus chunk; hard-capped at 64 MiB regardless of this value. |
| `LOCALDROP_UPLOAD_CHUNK_MIN_BYTES` | `65536` (64 KiB) | Smallest accepted tus chunk. |
| `LOCALDROP_UPLOAD_SESSIONS_MAX` | `20` | Concurrent active upload sessions per user. |
| `LOCALDROP_UPLOAD_TTL_DAYS` | `7` | Days an unfinished upload session survives before it is reclaimed. |
| `LOCALDROP_TRASH_RETENTION_DAYS` | `30` | How long deleted items stay in trash before auto-purge. |
| `LOCALDROP_SESSION_IDLE_MINUTES` | `10080` (7 days) | Sliding session expiry. |
| `LOCALDROP_SESSION_ABSOLUTE_MINUTES` | `43200` (30 days) | Hard session cap. A password change revokes every other session immediately. |
| `LOCALDROP_RATE_AUTH_LIMIT` | `10` | Auth requests per window, per IP. |
| `LOCALDROP_RATE_AUTH_WINDOW` | `300` (5 min) | Auth rate-limit window, seconds. |
| `LOCALDROP_RATE_AUTH_LOCKOUT` | `15` | Minutes of lockout after the auth limit is hit. |
| `LOCALDROP_RATE_SHARE_LIMIT` | `120` | Share requests per window, per IP. |
| `LOCALDROP_RATE_SHARE_WINDOW` | `60` | Share rate-limit window, seconds. |
| `LOCALDROP_RATE_CONTENT_LIMIT` | `60` | Content (download/preview) requests per window, per IP. |
| `LOCALDROP_RATE_CONTENT_WINDOW` | `60` | Content rate-limit window, seconds. |
| `LOCALDROP_RATE_API_LIMIT` | `600` | General API requests per window, per IP. |
| `LOCALDROP_RATE_API_WINDOW` | `60` | General API rate-limit window, seconds. |
| `LOCALDROP_ARGON2_TIME_COST` | `3` | argon2id time cost. Higher is slower to brute-force and slower to log in. |
| `LOCALDROP_ARGON2_MEMORY_COST` | `65536` (64 MiB) | argon2id memory cost, KiB. |
| `LOCALDROP_ARGON2_PARALLELISM` | `2` | argon2id lanes. |
| `LOCALDROP_LOG_LEVEL` | `INFO` | `DEBUG` is very verbose; never in production. |
| `LOCALDROP_LOG_FORMAT` | `json` | `json` for log aggregation, `console` (alias `dev`) for a human reading `journalctl`. |
| `LOCALDROP_DEV_MODE` | `false` | **Never in production.** Relaxes the secret-key requirement and enables `/api/docs` and CORS. |
| `LOCALDROP_CORS_ORIGINS` | *(empty)* | Dev only. Comma-separated origins, e.g. `http://localhost:5173` for `npm run dev`. |
| `LOCALDROP_MDNS_ENABLED` | `false` | Reserved for LAN service advertisement; not used by 1.1.0. |

### Read by the packaging, not by `config.py`

| Variable | Default | What |
|---|---|---|
| `LOCALDROP_HOST` | `0.0.0.0` | Bind address for the launcher. `127.0.0.1` makes LocalDrop reachable only through a local reverse proxy. |
| `LOCALDROP_PG_PORT` | `5439` | Port for the embedded PostgreSQL cluster. Change it if 5439 is taken. |
| `LOCALDROP_VERSION` | *(set at build)* | Version reported by `--version` and `GET /api/v1/version`. Injected by Docker and the frozen binary. |
| `LOCALDROP_BACKUP_BEFORE_MIGRATE` | `1` in compose | `pg_dump` to `$LOCALDROP_DATA_DIR/backups/` before auto-migrating. The container aborts on failure. |
| `POSTGRES_PASSWORD` | *(required, compose)* | Password for the compose `postgres` service; compose interpolates it into `LOCALDROP_DATABASE_URL`. |
| `LOCALDROP_IMAGE_TAG` | `stable` | Compose only. Image tag to pull, e.g. `1.1.0` to pin a reproducible deploy. |

## Reverse proxies

- Set `LOCALDROP_PUBLIC_URL` so share links point at the public address.
- Leave `LOCALDROP_TRUSTED_PROXIES=0` unless the proxy is genuinely the only
  path in. Each trusted hop lets the *previous* hop forge a client IP, which
  defeats per-IP rate limiting.
- Forward `X-Forwarded-Proto`. The app uses it to decide whether to set
  `Secure` on session cookies, so terminate TLS at the proxy.
- Raise the proxy's read timeout well above the default for large uploads and
  downloads. A streaming upload of a multi-gigabyte file can hold a request open
  for a long time; 3600s is a reasonable floor.

## Changing the data location

Inside the container, `LOCALDROP_DATA_DIR` must stay `/data` (the compose
`appdata` volume). If you bind-mount a host path instead, `chown` it to uid
`1000` (the container user) or the server exits with "not writable".

Moving a native install's data directory is safe — stored paths are relative —
but stop the service first, move the whole directory, and point the config at
the new path:

```bash
sudo systemctl stop localdrop
sudo mv /var/lib/localdrop /mnt/big/localdrop
sudo chown -R localdrop:localdrop /mnt/big/localdrop
sudo sed -i 's|^LOCALDROP_DATA_DIR=.*|LOCALDROP_DATA_DIR=/mnt/big/localdrop|' /etc/localdrop/localdrop.env
sudo systemctl start localdrop
```

## Checking what a running server thinks

```bash
curl -s http://127.0.0.1:8080/api/v1/version
curl -s http://127.0.0.1:8080/api/v1/health/ready
```

`/api/v1/health/ready` reports the database and storage probes individually, so
it is the fastest way to tell a misconfigured `LOCALDROP_DATA_DIR` from a
database that is simply down. Neither endpoint leaks configuration: `/version`
returns the build, not the environment.
