# Development

## Prerequisites

- Python 3.12+, Node 20.19+, PostgreSQL 16 on `127.0.0.1:5433`
- Windows: start PostgreSQL with the scheduled task `localdrop-pg` rather than
  calling `pg_ctl` directly — from an elevated shell, PostgreSQL's forked
  backends fail to initialise (`0xC0000142`). `scripts/dev-postgres.sh` wraps it.

```bash
# the easy way to get a database
docker run -d --name localdrop-pg -p 5433:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=localdrop_test postgres:16-alpine
```

## Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m localdrop.migrate            # apply migrations
python -m localdrop.launcher           # run it (embedded PostgreSQL, no setup)
```

For hot reload, run the app factory directly:

```bash
python -m uvicorn localdrop.main:create_app --factory --reload --port 8080
```

Config comes from the environment, or `backend/.env`. Set
`LOCALDROP_DEV_MODE=true` locally: it relaxes the secret-key requirement and
enables `/api/docs`.

### Tests

```bash
python -m pytest tests/ -q                 # everything (needs PostgreSQL)
python -m pytest tests/test_no_db.py -q    # fast subset, no database at all
python -m pytest tests/ -q -k "tus or share"
```

The suite is deliberately **unmocked**: real PostgreSQL, real filesystem. The
things most likely to break here — locking, `jsonb`, unique constraints, race
conditions — only break against a real database.

- `tests/test_v1_critical.py` — the critical path: auth, authz isolation, the
  file lifecycle, tus resume/checksum/oversize, dedup, share
  lifecycle/expiry/limits, hostile names, SVG-as-attachment, multi-range
  degradation, binary byte-identity.
- `tests/test_no_db.py` — health, request ids, security headers, the problem+json
  contract, LAN address discovery, version reporting, and the packaging
  invariants. Runs anywhere, in seconds.

## Frontend

```bash
cd frontend
npm ci
npm run dev        # :5173, proxies /api to :8080
npm run build      # emits into backend/src/localdrop/static
npm run lint       # oxlint
npm run typecheck  # tsc --noEmit
```

The build output is committed. That is deliberate (BC-9: the backend serves the
SPA, so a clone must be runnable without Node) — but it means **run
`npm run build` before you commit any frontend change**, or CI's
"the build must produce a SPA" check will catch it for you.

## Repository-level checks

```bash
python scripts/check_version.py           # one version, one source of truth
python scripts/check_config_docs.py        # CONFIGURATION.md matches config.py
python scripts/check_fr_traceability.py    # every FR has a test
```

All three run in CI. The first fails on a version literal anywhere it should
not be; the second on a setting that is undocumented or a default that has
drifted; the third on a new Must-have requirement with no test, or a
`KNOWN_GAPS` entry that has gone stale.

## Lint and types

```bash
cd backend
ruff check .            # lint
ruff format .           # format (do not hand-format)
ruff format --check .   # what CI runs
mypy src
```

## Building a binary

Only needed if you touch `packaging/`, the launcher, or the service files.

```bash
cd frontend && npm run build           # the backend serves the output
cd ../backend && python ../packaging/build-binary.py
```

PyInstaller cannot cross-compile, so this builds for your platform. The script
runs `localdrop --check` on the result and refuses to report success if the
bundle is missing its SPA, its migrations, or a C extension. Add `--zip` for a
portable archive, `--onefile`/`--onedir` to override the default layout
(onefile on Unix, one directory on Windows).

To check an existing install at any time:

```bash
localdrop --check
```

## Cutting a release

1. Bump `__version__` in `backend/src/localdrop/__about__.py`. It is the only
   place; everything else derives from it.
2. Add the release section to `CHANGELOG.md` and move `[Unreleased]` content
   into it.
3. Merge to `main`. CI must be green.
4. Tag and push:

   ```bash
   git tag -a v1.2.0 -m "1.2.0"
   git push origin v1.2.0
   ```

That is the whole process. The `release.yml` workflow then:

- builds binaries for `linux-x64`, `linux-arm64`, `macos-x64`, `macos-arm64`
  and `windows-x64`, plus the Windows installer and a portable zip;
- runs `localdrop --check` on each and refuses to publish a failing artefact;
- computes `SHA256SUMS` over everything;
- builds and pushes a multi-arch image to `ghcr.io` (`:1.2.0`, `:1.2`, `:stable`,
  `:latest`) with OCI labels and a provenance attestation;
- creates a GitHub Release whose notes come from the changelog section;
- commits the updated `VERSION` file and Homebrew formula;
- pushes the formula to the tap, if `TAP_REPO` and `TAP_TOKEN` are set.

The workflow refuses to start if the tag does not match `__version__`.

**Housekeeping for a maintainer**

| Secret / variable | Needed for |
|---|---|
| `GITHUB_TOKEN` | Built in; pushes the image and creates the Release |
| `TAP_REPO` | Repository variable, e.g. `Abhi-Subedi/homebrew-localdrop` |
| `TAP_TOKEN` | Secret: a fine-grained PAT with `contents: write` on the tap |

Without the tap credentials the release still completes; the formula is
committed to the repository and a maintainer runs `brew tap-update` by hand.

## Layout

```
backend/src/localdrop/          the importable package
  api/                          HTTP routers
  services/                     domain logic (tree, uploads, shares, accounts…)
  models/                       SQLAlchemy tables
  storage.py                    the only module allowed to touch the data dir
  launcher.py                   `localdrop` — every install method uses this
  migrate.py                    programmatic Alembic upgrades
  service.py                    macOS LaunchAgent management
  migrations/                   Alembic, hand-written, forward-only
  static/                       the built SPA (emitted by frontend/)
backend/tests/                  pytest, no mocks
backend/scripts/smoke_flow.py   end-to-end happy path against a running server
frontend/src/                   React SPA (pages/, api.ts, uploader.ts)
packaging/
  pyinstaller/                  the spec + entry shim
  linux/ systemd unit + env template
  macos/  launchd plist + env template
  windows/ Inno Setup script
  homebrew/ the formula
  build-binary.py               the build driver
docker/                         Dockerfile + entrypoint.sh
scripts/                        backup/restore, dev-postgres, check_* scripts
docs/                           user docs + spec/ + adr/
```

## Rules of the road

- **Vertical slices:** a feature is not done until DB + API + UI + tests land.
- **One process.** The API, tus endpoint, downloads and the SPA are served by
  the same FastAPI app. Do not add a second runtime or a Node process.
- **Storage first, DB second**, on every mutation. A crash then leaves an
  orphan for the GC to reclaim, never a dangling row.
- **No whole-file buffering.** Uploads and downloads stream with bounded RAM.
- **No user string reaches a filesystem path.** Names go through one validator;
  storage paths are built from UUIDs and hashes only, with a containment check.
- **Only `storage.py` touches the data directory.** If you need a new
  filesystem operation, add it there — it is where the three defences live.
- **Stored paths are relative** to the data directory, so a restore to a
  different location works. Keep it that way.
- **`O_BINARY` on every `os.open`** in the storage path. Windows text-mode
  translation silently corrupts bytes; there is a regression test for it.
- **UTC everywhere.** The database session is UTC; HTTP dates serialise in UTC.
- **Migrations are hand-written and forward-only.** Never use `autogenerate`,
  never edit an applied migration, add a new one.
- **Configuration is `LOCALDROP_*` env vars** defined in `config.py`. Adding one
  means adding it to `docs/CONFIGURATION.md` too, or CI fails.
- **Trace requirements to tests.** Name the `FR-xN` id in the test.
