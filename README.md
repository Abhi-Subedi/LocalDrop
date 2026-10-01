# LocalDrop

**Self-hosted, local-network-first file sharing. Fast, private, and yours.**

Upload from your laptop, download on your phone. No cloud account, no telemetry,
no vendor lock-in — one server on your network holds your files.

- **Resumable uploads** — interrupted transfer? It picks up where it stopped,
  even after a browser restart.
- **Real files welcome** — multi-gigabyte videos stream in chunks; the server
  never loads a whole file into RAM.
- **Share links with teeth** — expiry dates, download limits, passwords,
  revocation, and QR codes for the couch-to-phone handoff.
- **Clean file manager** — folders, search, sort, previews, trash with restore.
  Mobile-friendly, keyboard-navigable, dark-mode aware.
- **Installs in one command** — Docker, a Linux binary, Homebrew, or a Windows
  installer. A native install needs no database and no container runtime.

## Try it

**There is a live demo.** Open the URL, and you get your own throwaway account
with an empty file tree — no setup, no password, no configuration. Upload
something, share it, download it back.

Everything you upload is deleted after an hour, and the whole instance is torn
down when the workflow ends. It is a demonstration, not a service: see
[docs/DEMO.md](docs/DEMO.md).

To start one yourself:

```bash
gh workflow run demo.yml
```

## Install

Pick the line for your platform. All of them end with LocalDrop serving on
`http://<your-lan-ip>:8080`.

### Docker (any platform with Docker)

```bash
git clone https://github.com/Abhi-Subedi/LocalDrop.git && cd LocalDrop
cp .env.example .env      # set LOCALDROP_SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d
docker compose logs -f app
```

The image is pulled from `ghcr.io` — no build step.

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sudo sh
```

Installs a `localdrop` system account, `/var/lib/localdrop`, a hardened systemd
unit, and starts the service. Manage it with `systemctl status localdrop`.

Prefer to read the script first?

```bash
curl -fsSLO https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh
less install.sh && sudo sh install.sh
```

### macOS

```bash
brew install abhi-subedi/localdrop/localdrop
localdrop                        # or: localdrop install-service
```

Or the same installer as Linux, which sets up a system-wide launchd job:

```bash
curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sudo sh
```

### Windows

Download **`LocalDrop-<version>-windows-x64-setup.exe`** from the
[releases page](https://github.com/Abhi-Subedi/LocalDrop/releases) and run it —
Start Menu shortcut, optional start-at-login, proper uninstaller. There is also a
portable zip if you would rather not install anything.

From PowerShell, the scripted route:

```powershell
irm https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.ps1 | iex
```

### From source

```bash
cd backend && pip install -e ".[dev]"
cd ../frontend && npm ci && npm run build && cd ..
cd backend && localdrop
```

Every installer verifies the download's SHA-256 before unpacking anything, and
runs `localdrop --check` to confirm the install works before reporting success.

**Full instructions, first-run setup, and reverse proxies:**
[docs/INSTALLATION.md](docs/INSTALLATION.md).

## Finish setup

On first run LocalDrop prints a one-time setup token. Open the URL it gives you,
paste the token, and create your owner account. That account owns everything.

Headless install? Get the token whenever you need it:

```bash
localdrop --setup-token                     # native
docker compose logs app | grep -i 'token'   # Docker
```

Then open LocalDrop from your phone and drop in a file.

## How it works

```
Browser ──▶ LocalDrop (one FastAPI process serves API + web UI)
               ├── PostgreSQL 16        (metadata: tree, users, sessions, shares)
               └── one data directory   (file bytes: content-addressed blobs)
```

On a native install with no `LOCALDROP_DATABASE_URL` set, the embedded
PostgreSQL lives inside that same data directory — so backing up LocalDrop means
backing up one folder.

Uploads speak the [tus](https://tus.io) resumable-upload protocol
(`creation` + `termination` + server-side `checksum`); downloads stream with
single-range resume support. Details: [API.md](docs/API.md).

## Documentation

| Guide | What |
|---|---|
| [INSTALLATION.md](docs/INSTALLATION.md) | Every install method, first-run setup, LAN access, reverse proxy, upgrade |
| [DEMO.md](docs/DEMO.md) | Running the public demo, and what demo mode does |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable, with defaults |
| [BACKUP.md](docs/BACKUP.md) | What to back up, `backup.sh` / `restore.sh`, restore drill |
| [SECURITY.md](docs/SECURITY.md) | Threat model, hardening checklist |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |
| [SUPPORT.md](SUPPORT.md) | Where to ask for help |
| [API.md](docs/API.md) | REST v1 reference (auth, files, tus uploads, shares) |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local dev setup, tests, release process |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

Engineering history — the full specification, the ADRs, and the implementation
plan — lives in [`docs/spec/`](docs/spec/) and [`docs/adr/`](docs/adr/).

## Status

1.1.0 is a working release. Known limits, stated plainly:

- Single owner account. One account owns everything; sharing with other *users*
  is not a feature — use public share links.
- Files live in folders. No top-level files, no folder or zip download.
- No live cross-device refresh. The UI updates after your own actions; another
  device's changes show up on reload.
- LAN discovery is a URL and a QR code, not mDNS.
- Windows binaries are unsigned, so SmartScreen warns on first run.

See [CHANGELOG.md](CHANGELOG.md) for the full picture, including the nine
Must-have requirements that have no automated test and why.

## Contributing

Bug reports, tests and documentation are all welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). A PR with a test that fails without the fix
is worth more than one without.

Security problems go through private reporting, not public issues:
[SECURITY.md](SECURITY.md).

## License

[GNU Affero General Public License v3.0](LICENSE) — if you host a modified
LocalDrop as a network service, you must offer your modified source to your
users. This is a deliberate choice, not an oversight; the reasoning is in
[ADR-010](docs/adr/ADR-010-license.md).
