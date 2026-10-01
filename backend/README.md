# LocalDrop — backend

The FastAPI server, database layer and CLI entrypoint for LocalDrop. One
process serves the JSON API, the tus upload endpoint, streaming downloads and
the compiled web UI.

Full project documentation lives in the [repository root](../README.md) and
[`docs/`](../docs/).

## Install

```bash
pip install localdrop            # from a published wheel
pip install -e ".[dev]"          # from a source checkout, with the test tools
```

## Run

```bash
localdrop                       # data dir + embedded PostgreSQL, no setup
localdrop --port 9000 --data-dir /srv/localdrop
```

With Docker or systemd, set `LOCALDROP_DATABASE_URL` to your own PostgreSQL and
the embedded cluster is never started.

## Develop

```bash
python -m pytest tests/ -q       # needs PostgreSQL on 127.0.0.1:5433
ruff check . && ruff format --check .
mypy src
python -m localdrop.migrate      # apply migrations
python -m uvicorn localdrop.main:create_app --factory --reload --port 8080
```

## Layout

| Path | What |
|---|---|
| `src/localdrop/` | the importable package (API, services, storage, launcher) |
| `src/localdrop/migrations/` | Alembic environment, forward-only |
| `src/localdrop/static/` | the built SPA (emitted here by `frontend/`) |
| `tests/` | pytest suite, no mocks — real PostgreSQL |
| `scripts/smoke_flow.py` | end-to-end happy path against a running server |

## Licence

AGPL-3.0-only. See [`LICENSE`](../LICENSE).
