# Installation

LocalDrop runs on Linux, macOS, Windows, and in Docker. Every method below ends
with the same thing: a web UI on `http://<your-lan-ip>:8080` and a one-time
setup token to create your owner account.

**Requirements**

| Method | You need |
|---|---|
| Docker | Docker Engine 20+ with the Compose plugin, 64-bit |
| Linux | glibc 2.28+ (Debian 10+, Ubuntu 20.04+, RHEL 8+), x86-64 or arm64, systemd |
| macOS | macOS 11+, Intel or Apple Silicon |
| Windows | Windows 10 64-bit or later |
| From source | Python 3.12+, Node 20.19+, PostgreSQL 16 |

No method needs a separate database. If you do not set
`LOCALDROP_DATABASE_URL`, LocalDrop starts its own embedded PostgreSQL inside
its data directory, so the whole server is one binary and one folder.

---

## Choose your method

- [Docker](#docker) — any platform with a container runtime
- [Linux](#linux) — systemd, one command
- [macOS](#macos) — Homebrew, or the same installer as Linux
- [Windows](#windows) — installer, or portable
- [From source](#from-source) — for development and for patching

Whichever you pick, the last three steps — setup token, owner account, first
upload — are identical. They are in [Finish setup](#finish-setup).

---

## Docker

```bash
git clone https://github.com/Abhi-Subedi/LocalDrop.git && cd LocalDrop
cp .env.example .env
```

Edit `.env` and set the two required values:

```bash
LOCALDROP_SECRET_KEY=<at least 32 random characters>
POSTGRES_PASSWORD=<a strong database password>
```

Generate them with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Then start it. The image is pulled from GitHub Container Registry, so there is
no build step:

```bash
docker compose up -d
docker compose logs -f app
```

The log prints your LAN URL and a QR code.

**Optional:** `LOCALDROP_HOST_PORT` (default `8080`) if the port is taken.
`LOCALDROP_IMAGE_TAG=1.1.0` in `.env` pins a specific version instead of
tracking `:stable`. Everything else: [CONFIGURATION.md](CONFIGURATION.md).

### Running without the repository

You do not need the source tree. Write a minimal compose file:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: localdrop
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
      POSTGRES_DB: localdrop
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U localdrop -d localdrop"]
      interval: 10s
      retries: 5
  app:
    image: ghcr.io/abhi-subedi/localdrop:stable
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
    environment:
      LOCALDROP_DATABASE_URL: postgresql+psycopg://localdrop:${POSTGRES_PASSWORD}@db:5432/localdrop
      LOCALDROP_SECRET_KEY: ${LOCALDROP_SECRET_KEY:?set LOCALDROP_SECRET_KEY}
      LOCALDROP_DATA_DIR: /data
      LOCALDROP_PUBLIC_URL: ${LOCALDROP_PUBLIC_URL:-}
    volumes: [appdata:/data]
    ports: ["8080:8080"]
volumes: { pgdata: , appdata: }
```

---

## Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sudo sh
```

That downloads the binary for your architecture, verifies its SHA-256, creates a
locked `localdrop` system account, sets up `/var/lib/localdrop` and
`/etc/localdrop/localdrop.env`, installs a sandboxed systemd unit, and starts
the service.

**Read it first** — piping a script into a shell deserves five seconds of
thought:

```bash
curl -fsSLO https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh
less install.sh && sudo sh install.sh
```

### Installer options

| Option | Effect |
|---|---|
| `--version 1.1.0` | Install a specific release instead of the newest |
| `--port 9000` | Listen on a different port |
| `--data-dir /mnt/big/localdrop` | Store files somewhere with more room |
| `--no-start` | Install everything, do not start the service yet |
| `--no-service` | Install the binary only — no account, no service |
| `--prefix ~/.local` | Install the binary somewhere other than `/usr/local/bin` |

```bash
sudo sh install.sh --version 1.1.0 --port 9000
sudo sh install.sh --no-service     # e.g. on a host without systemd
```

### Operating it

```bash
systemctl status localdrop
systemctl restart localdrop
journalctl -u localdrop -f
```

Configuration lives in `/etc/localdrop/localdrop.env`. Edit it, then
`systemctl restart localdrop`.

### Without systemd

NixOS, OpenWrt, and some embedded systems have no systemd. Use
`--no-service` and manage the process yourself:

```bash
sudo sh install.sh --no-service
sudo -u localdrop /usr/local/bin/localdrop --data-dir /var/lib/localdrop --no-browser
```

### Uninstall

```bash
sudo sh uninstall.sh            # keeps your data
sudo sh uninstall.sh --purge    # deletes data and config, after confirming
```

---

## macOS

### Homebrew

```bash
brew install abhi-subedi/localdrop/localdrop
localdrop                      # start it
```

Homebrew will not install a service for you, and should not. Two options:

```bash
localdrop                      # run it in a terminal; Ctrl-C to stop
localdrop install-service      # start it at login via launchd
localdrop uninstall-service    # undo that
```

Data lives in `~/Library/Application Support/LocalDrop`.

### System-wide (the Linux installer)

If you want LocalDrop to run for the whole machine rather than one user, the
same installer works and sets up a launchd **LaunchDaemon**:

```bash
curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sudo sh
sudo launchctl print system/io.github.abhisubedi.localdrop   # status
```

Config: `/etc/localdrop/localdrop.env`. Logs: `/var/lib/localdrop/localdrop.log`.

---

## Windows

### The installer (recommended)

Download **`LocalDrop-<version>-windows-x64-setup.exe`** from the
[releases page](https://github.com/Abhi-Subedi/LocalDrop/releases) and run it.

It installs per-user (no administrator rights needed), creates Start Menu and
desktop shortcuts, can add a start-at-login shortcut, and registers a proper
uninstaller under Settings → Apps.

> The binaries are not code-signed, so SmartScreen shows a warning on first
> run. Choose **More info → Run anyway** if you downloaded it from the official
> releases page. Verify the download if you are unsure:
> `Get-FileHash .\LocalDrop-1.1.0-windows-x64-setup.exe -Algorithm SHA256` and
> compare it with the `SHA256SUMS` from the same release.

### Portable

Grab **`LocalDrop-<version>-windows-x64.zip`**, extract it, and run
`localdrop.exe` from the folder. It manages its own data in
`%LOCALAPPDATA%\LocalDrop`. Nothing is registered; delete the folder to
uninstall.

### From PowerShell

```powershell
irm https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.ps1 | iex
```

This downloads, verifies, installs, and then runs `localdrop --check` to prove
the install works before it reports success. Options:

```powershell
.\install.ps1 -Version 1.1.0        # a specific release
.\install.ps1 -StartServer          # launch it when you are done
.\install.ps1 -NoShortcuts          # no Start Menu or desktop entry
```

---

## From source

You need Python 3.12+, Node 20.19+, and a PostgreSQL 16 you can reach.

```bash
git clone https://github.com/Abhi-Subedi/LocalDrop.git && cd LocalDrop

cd backend
python -m venv .venv
source .venv/Scripts/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cd ../frontend
npm ci && npm run build             # emits into backend/src/localdrop/static

cd ../backend
alembic upgrade head                # or: python -m localdrop.migrate
localdrop
```

`localdrop` uses `LOCALDROP_DATABASE_URL` if set, and otherwise starts an
embedded PostgreSQL in the per-user data directory — which is usually what you
want while developing.

More: [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Finish setup

Identical for every install method.

**1. Get the token.** On first run the server prints a one-time setup token,
valid for 15 minutes. It is in the log:

```bash
docker compose logs app | grep -i 'setup token'          # Docker
journalctl -u localdrop -n 50 --no-pager                 # Linux systemd
log show --predicate 'process == "localdrop"' --last 5m # macOS
```

If you missed it — or need a fresh one — ask any time:

```bash
localdrop --setup-token
```

It only prints while onboarding is incomplete.

**2. Create the owner account.** Open the printed URL on any device on the same
network (or scan the QR code with your phone), paste the token, and choose a
username and password.

There is no open registration. This one account owns the server — that is the
V1 model, not an oversight.

**3. Drop in a file.** Create a folder, open it, drag files in. Select a file
and choose **Share** to mint a link with an optional expiry, download limit and
password.

---

## LAN access

- Devices must be on the same network unless you expose the server further.
- The startup log prints every detected LAN IPv4. If one does not work from your
  phone, try another — VMs, VPNs and Docker bridges add addresses that are not
  reachable from a phone.
- The QR code in the log and on the setup page is the fastest way to open the UI
  on a phone.

## Reverse proxy

Only needed for access beyond your LAN. **Terminate TLS at the proxy** — session
cookies and share passwords travel in the clear otherwise.

Put Caddy, nginx or Tailscale in front of LocalDrop, set
`LOCALDROP_PUBLIC_URL=https://your-host` so share links point at the right
place, and leave `LOCALDROP_TRUSTED_PROXIES=0` unless the proxy is genuinely the
only path in.

```nginx
server {
    listen 443 ssl;
    server_name files.example.com;

    # Large uploads and long downloads need a generous read timeout.
    client_max_body_size 0;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Read [SECURITY.md](SECURITY.md) before exposing LocalDrop to a network you do
not control.

## Upgrading

> Migrations are **forward-only**. Downgrades are unsupported; recovery means
> restoring a backup. Take one before anything other than a patch release.

```bash
./scripts/backup.sh                        # Docker: see docs/BACKUP.md
```

| Method | Upgrade |
|---|---|
| Docker | `docker compose pull && docker compose up -d` |
| Linux | `sudo sh install.sh` (keeps your data and config) |
| macOS (Homebrew) | `brew upgrade localdrop` |
| macOS (install.sh) | `sudo sh install.sh` |
| Windows (installer) | Run the new `setup.exe` over the top |
| Windows (portable) | Replace the folder |
| Source | `git pull`, `pip install -e ".[dev]"`, `npm ci && npm run build`, restart |

The Docker entrypoint writes a `pg_dump` to the data volume before migrating and
**refuses to start** if that backup fails. Native installs apply migrations on
start; take a backup first ([BACKUP.md](BACKUP.md)).

After upgrading, check that it came up:

```bash
curl -s http://127.0.0.1:8080/api/v1/health/ready   # {"status":"ok",...}
curl -s http://127.0.0.1:8080/api/v1/version       # the version now running
```

## Uninstall

```bash
# Docker
docker compose down -v     # WARNING: deletes the database AND all your files

# Linux / macOS native
sudo sh uninstall.sh           # stops the service, keeps data
sudo sh uninstall.sh --purge   # also deletes data and config

# Windows
# Settings -> Apps -> LocalDrop
```

Take a backup first if there is anything on the server you care about:
[BACKUP.md](BACKUP.md).

## Troubleshooting

**`localdrop --check` fails.** It prints what is missing — a bundled resource, a
C extension, or the app factory. A truncated download is the usual cause;
re-download and compare against `SHA256SUMS`.

**Readiness says `degraded`.** It names the subsystem: `database` or `storage`.
For `storage`, the data directory is not writable by the account LocalDrop runs
as — on Docker that means uid 1000 does not own your bind mount.

**The setup page says onboarding is complete but you cannot sign in.** Someone
else claimed it, or you are pointed at a different server. `localdrop
--setup-token` will tell you which case it is.

**A phone cannot reach the URL.** Check that both devices are on the same
network and that your firewall allows the port. Try another address from the
startup log.

**Port 8080 is already in use.** `--port 9000` for the native installer, or
`LOCALDROP_HOST_PORT=9000` in `.env` for Docker.
