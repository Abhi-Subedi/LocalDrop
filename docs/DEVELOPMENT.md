# Development

## Prereqs

- Python 3.12+, Node 20+, PostgreSQL 16 (local instance for tests/dev).
- Windows dev note: start the bundled Postgres with the scheduled task
  `localdrop-pg` (direct `pg_ctl` from some shells spawns broken children);
  it listens on `127.0.0.1:5433`.

## Backend

```bash
cd backend
.venv/Scripts/activate  # or python -m venv .venv && pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn localdrop.main:create_app --factory --reload --port 8080
```

Config comes from env / `backend/.env` (`LOCALDROP_DEV_MODE=true` for local).
Run the suite (needs Postgres on `:5433` with `localdrop_test` database):

```bash
python -m pytest tests/ -q
```

The critical-path suite (`tests/test_v1_critical.py`, 26 tests) covers auth,
authz isolation, file lifecycle, tus resume/checksum/oversize, dedup,
sharing lifecycle/expiry/limits, hostile names, SVG-as-attachment,
multi-range degradation, and binary byte-identity.

## Frontend

```bash
cd frontend
npm install
npm run dev      # :5173, proxies /api to :8080
npm run build    # emits into backend/static (served by FastAPI, single process)
```

## Layout

```
backend/src/localdrop/   FastAPI app (api/, services/, models/, storage.py, …)
backend/migrations/      Alembic, hand-written, forward-only (0001 = V1 schema)
backend/tests/           Critical-path suite (real Postgres, no mocks)
frontend/src/            React SPA (pages/, api.ts, uploader.ts tus client)
docker/                  Production Dockerfile + entrypoint
docker-compose.yml       Prod stack (app + postgres:16-alpine)
scripts/                 backup.sh, restore.sh, dev-postgres.sh
docs/                    User docs (this file's siblings) + spec/ + adr/
```

## Rules of the road

- **Vertical slices:** a feature isn't done until DB + API + UI + tests land.
- **Storage-first, DB-second** on every mutation (crashes leave orphans for
  GC, never dangling rows). No whole-file buffering anywhere (bounded RAM).
- **No user string reaches a filesystem path** — names validate through one
  validator; storage paths use UUIDs/hashes only, with containment checks.
- **Binary discipline:** every `os.open` in the storage path forces
  `O_BINARY` (Windows text-mode translation corrupts bytes) — see the
  `test_upload_binary_content_roundtrip_byte_identical` regression test.
- Timezone discipline: DB session is UTC; HTTP dates serialize in UTC.
- Migrations are hand-written and reviewed; never edit an applied migration,
  add a new one.
