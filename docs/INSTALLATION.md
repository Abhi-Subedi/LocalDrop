# Installation

LocalDrop V1 runs as two Docker containers (app + PostgreSQL). You need a
64-bit Linux host with [Docker Engine](https://docs.docker.com/engine/install/)
and the Compose plugin (`docker compose version` should answer).

## 1. Configure

```bash
git clone <this-repo> localdrop && cd localdrop
cp .env.example .env
```

Edit `.env` — the two values you **must** set:

```bash
LOCALDROP_SECRET_KEY=<at least 32 random characters>
POSTGRES_PASSWORD=<a strong database password>
```

Generate them:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Optional: `LOCALDROP_HOST_PORT` (default `8080`) if the port is taken,
`LOCALDROP_PUBLIC_URL` if you serve behind a reverse proxy (share links and
QR codes will use it). Everything else: [CONFIGURATION.md](CONFIGURATION.md).

## 2. Start

```bash
docker compose up -d --build
docker compose logs -f app
```

The log prints your LAN URLs plus a QR code, e.g.:

```
LocalDrop is running:
    http://192.168.1.20:8080
```

On first boot the database is empty, so the app prints a **setup token** into
its log (valid 15 minutes, single use). If you miss it, the setup page mints
a fresh one on load — or fetch one directly:

```bash
curl http://<server>:8080/api/v1/setup/token
```

## 3. Create your account

Open the URL on any device on the same network (or scan the QR with your
phone). Enter the setup token, pick a username and password — that's the
**owner** account. There is no open registration in V1; this one account owns
the server.

## 4. Use it

Create a folder → open it → **Upload** (or drag & drop files anywhere in the
folder). Select a file → **Share** to mint a link with optional expiry,
download limit, and password. Trash keeps deleted files for 30 days.

## LAN access notes

- Same Wi-Fi/network is required unless you expose the server further.
- The server prints every detected LAN IPv4; if one doesn't work from a
  device, try the others (VMs, VPNs, and Docker bridges add addresses that
  aren't reachable from your phone).
- Phones: the QR code in the server log (and on the setup page) is the
  fastest way to open the UI or a share link.

## Reverse proxy (optional, recommended for remote access)

Run a proxy (Caddy/Traefik/nginx) on your network that forwards to
`http://<server>:8080`, set `LOCALDROP_PUBLIC_URL=https://your-host`, and
keep `LOCALDROP_TRUSTED_PROXIES` at `0` unless the proxy is the *only*
client (see [SECURITY.md](SECURITY.md#reverse-proxies)). Serve public traffic
over HTTPS — share passwords and session cookies travel over the wire.

Tailscale users: `tailscale serve` to the LAN port works with no extra config.

## Upgrading

```bash
git pull
docker compose up -d --build
```

The entrypoint takes a database backup into the data volume, then applies
migrations automatically. Check `docker compose logs app` after upgrading.

## Uninstall

```bash
docker compose down -v   # WARNING: deletes the database AND all files
```

Keep backups first: [BACKUP.md](BACKUP.md).
