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
- **Boring deployment** — one `docker compose up`, two containers
  (app + PostgreSQL), one data volume.

## Quickstart (5 minutes)

```bash
git clone <this-repo> localdrop && cd localdrop
cp .env.example .env
# edit .env: set LOCALDROP_SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d --build
docker compose logs -f app   # shows your LAN URLs + first-run setup token
```

Open the printed URL (e.g. `http://192.168.1.20:8080`), enter the setup token to
create your owner account, and drop in your first file. Full steps:
[INSTALLATION.md](docs/INSTALLATION.md).

## How it works

```
Browser ──▶ LocalDrop (FastAPI serves API + web UI)
               ├── PostgreSQL 16 (metadata: tree, users, sessions, shares)
               └── /data volume  (file bytes: content-addressed blob store)
```

Uploads speak the [tus](https://tus.io) resumable-upload protocol
(`creation` + `termination` + server-side `checksum`); downloads stream with
single-range resume support. Details: [API.md](docs/API.md).

## Documentation

| Guide | What |
|---|---|
| [INSTALLATION.md](docs/INSTALLATION.md) | Install with Docker, first-run setup, LAN access, reverse proxy |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable, with defaults |
| [BACKUP.md](docs/BACKUP.md) | What to back up, `backup.sh` / `restore.sh`, restore drill |
| [SECURITY.md](docs/SECURITY.md) | Threat model, hardening checklist, reporting a vulnerability |
| [API.md](docs/API.md) | REST v1 reference (auth, files, tus uploads, shares) |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local dev setup, tests, project layout |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

Engineering history (spec, ADRs, implementation plan) lives in
[`docs/spec/`](docs/spec/) and [`docs/adr/`](docs/adr/).

## Status & limits (V1)

Single-owner server: one account owns everything (sharing with other *users*
is not a V1 feature — use public share links instead). Files live in folders;
moving a file to the top level is not supported. See
[CHANGELOG.md](CHANGELOG.md) for what's new and known limitations.

## License

[GNU Affero General Public License v3.0](LICENSE) — if you host a modified
LocalDrop as a network service, share your modified source with your users.
