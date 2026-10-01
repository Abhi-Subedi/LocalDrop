# Configuration

All settings arrive as `LOCALDROP_*` environment variables (12-factor). In
the Docker stack, set them in `.env` (see `.env.example`); the compose file
passes them into the `app` container.

## Reference

| Variable | Default | What |
|---|---|---|
| `LOCALDROP_SECRET_KEY` | *(required)* | HMAC/session secret, **≥ 32 chars**. Server refuses to boot without it (unless dev mode). |
| `POSTGRES_PASSWORD` | *(required)* | Database password (compose only; wired into `DATABASE_URL`). |
| `LOCALDROP_HOST_PORT` | `8080` | Host port published by compose (container listens on `LOCALDROP_PORT`). |
| `LOCALDROP_PUBLIC_URL` | empty | Public base URL for share links/QR (e.g. `https://files.example.com`). Empty = derive per request. |
| `LOCALDROP_DATABASE_URL` | compose default | SQLAlchemy URL, `postgresql+psycopg://…`. |
| `LOCALDROP_DATA_DIR` | `/data` (container) | File storage root. Paths are stored relative to it, so backup/restore to a different location works — but keep it stable anyway. |
| `LOCALDROP_PORT` | `8080` | Port the server listens on. |
| `LOCALDROP_MAX_UPLOAD_BYTES` | `107374182400` (100 GiB) | Max single-file upload; bigger → `413`. `0` = unlimited (not recommended). |
| `LOCALDROP_UPLOAD_SESSIONS_MAX` | `20` | Concurrent active upload sessions per user. |
| `LOCALDROP_TRASH_RETENTION_DAYS` | `30` | Trash auto-purge horizon. |
| `LOCALDROP_SESSION_IDLE_MINUTES` | `10080` (7 d) | Sliding session expiry. |
| `LOCALDROP_SESSION_ABSOLUTE_MINUTES` | `43200` (30 d) | Hard session cap (password change revokes others immediately). |
| `LOCALDROP_TRUSTED_PROXIES` | `0` | `X-Forwarded-For` hops to trust for rate limiting. `0` = socket peer (spoof-proof). |
| `LOCALDROP_LOG_FORMAT` | `json` | `json` (production) or `dev` (human-readable). |
| `LOCALDROP_LOG_LEVEL` | `INFO` | `DEBUG` is very verbose; never in production. |
| `LOCALDROP_BACKUP_BEFORE_MIGRATE` | `1` (compose) | `pg_dump` to `/data/backups/` before auto-migrations. |
| `LOCALDROP_DEV_MODE` | unset | **Never in production.** Relaxes secret requirements, enables docs/CORS. |

## Reverse proxies

- Set `LOCALDROP_PUBLIC_URL` so share links point at the public address.
- Leave `TRUSTED_PROXIES=0` (Direct) unless the proxy is the only client;
  each trusted hop lets the *previous* hop spoof client IPs (rate-limit bypass).
- Forwarded proto: the app honors `X-Forwarded-Proto` for secure-cookie
  decisions — terminate TLS at the proxy.

## Changing data locations

`LOCALDROP_DATA_DIR` inside the container must stay `/data` (compose volume
`appdata`). If you bind-mount a host path instead, `chown` it to uid `1000`
(the container user) or the server exits with "not writable".
