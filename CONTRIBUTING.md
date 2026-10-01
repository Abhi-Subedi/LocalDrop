# Contributing to LocalDrop

Thanks for considering it. LocalDrop is a small project maintained in spare
time, so contributions that come with a test and pass CI are worth far more than
elaborate ones that do not.

Read this before you start. It is short.

## The short version

1. Open an issue first for anything beyond a trivial fix. It saves you the
   work of building something that will not be merged.
2. Set up the dev environment below (about 5 minutes).
3. Make the change, add a test, run the checks.
4. Open a PR and fill in the template.

## Code of conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies everywhere. It is short and it
is enforced.

## Development setup

You need **Python 3.12+**, **Node 20.19+** and a **PostgreSQL 16** you can
connect to on `127.0.0.1:5433`.

```bash
git clone https://github.com/Abhi-Subedi/LocalDrop.git
cd LocalDrop

# backend
cd backend
python -m venv .venv
source .venv/Scripts/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# frontend
cd ../frontend
npm ci
```

The test suite is **not** mocked: it runs against a real PostgreSQL, because
the things most likely to break (locking, constraints, `jsonb`) only break
against a real database. The easiest way to get one:

```bash
docker run -d --name localdrop-pg -p 5433:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=localdrop_test postgres:16-alpine
```

If you are on Windows and Docker is awkward, `scripts/dev-postgres.sh` drives a
Zonky embedded PostgreSQL for you.

## The checks

Run these before you push. CI runs the same commands, so anything that passes
locally passes there.

```bash
# backend
cd backend
ruff check .
ruff format --check .
mypy src
python -m pytest tests/ -q
python -m pytest tests/test_no_db.py -q      # the fast subset, no database

# frontend
cd ../frontend
npm run lint
npm run typecheck
npm run build

# repository-level
python scripts/check_version.py              # one version, one source of truth
python scripts/check_config_docs.py           # CONFIGURATION.md matches config.py
python scripts/check_fr_traceability.py       # every FR has a test
```

`tests/test_no_db.py` runs in seconds and needs no database — use it while you
iterate, and the full suite before you open the PR.

### Building a binary

```bash
cd frontend && npm run build                   # the backend serves the output
cd ../backend && python ../packaging/build-binary.py
```

That produces a self-contained server in `dist/release/` and runs
`localdrop --check` on it before declaring success. You do not need this unless
you are changing `packaging/`, the launcher, or the service files.

## Code style

**Do not argue about style.** `ruff` and `oxlint` decide, and they are already
configured. Run the formatter rather than hand-formatting:

```bash
ruff format .        # backend
```

Conventions worth knowing, because they are not obvious from the linter:

- **The backend is one process.** The API, the tus endpoint, downloads and the
  compiled web UI are all served by the same FastAPI app. Do not add a second
  runtime, a Node process, or a separate static host.
- **All configuration is `LOCALDROP_*` environment variables**, defined in
  `backend/src/localdrop/config.py`. If you add a setting, add it there *and*
  to `docs/CONFIGURATION.md` — CI fails otherwise.
- **The version lives in exactly one place**, `backend/src/localdrop/__about__.py`.
  Never write a version literal anywhere else. `scripts/check_version.py`
  enforces this.
- **Only `storage.py` touches the data directory.** It enforces three things:
  paths built only from UUIDs and hashes, a containment check, and
  `O_NOFOLLOW | O_CREAT | O_EXCL`. Do not bypass it; extend it.
- **Stored paths are relative to the data dir** so a backup restores to a
  different location. Keep it that way.
- **Forward-only migrations, hand-written.** Do not use `autogenerate`, and do
  not edit a migration that has shipped. Add a new one.
- **Front-end state is server state.** Data comes from `api.ts`; components do
  not call `fetch` directly. Local UI state goes in `zustand`.
- **Comments explain why, not what.** The codebase has explanatory comments
  where the reasoning is non-obvious; it does not narrate its own code.

## Testing expectations

- **A bug fix comes with a test that fails without the fix.** This is not
  negotiable; it is the single most useful thing you can contribute.
- **A new feature comes with a test**, and the test names the requirement id
  (`FR-xN`) in its name or docstring. `scripts/check_fr_traceability.py` maps
  requirements to tests and fails on a new uncovered one.
- Prefer real assertions over mocks. The existing suite uses a real database and
  a real filesystem on purpose.
- Do not weaken a test to make it pass. If a test is wrong, fix the test *and*
  say why in the PR.
- If you close a known gap in `KNOWN_GAPS` (see
  `scripts/check_fr_traceability.py`), remove the entry — CI tells you when it
  is stale.

## Commits and pull requests

- One logical change per PR. A refactor and a behaviour change in the same PR
  makes review guesswork.
- Commit messages explain **why**. "Fix the upload race" is useless;
  "Cancel a tus session before hashing so an interrupted chunk cannot leave a
  staging file that dedup then promotes" tells a future reader what the code is
  for.
- Fill in the PR template, especially the **Risk** section. If you touch auth,
  storage paths, or upload handling, say so explicitly.
- Update `CHANGELOG.md` under `[Unreleased]` for anything a user would notice.
- Update `docs/` when you change behaviour or configuration. Docs are part of
  the change, not a follow-up.

## Good first issues

There is no formal label, but these are genuinely useful and small:

- Add a test for an entry in `KNOWN_GAPS` in `scripts/check_fr_traceability.py`.
- Fill in an empty section in `docs/`, or fix something that is now wrong in it.
- Improve an error message so the next person who hits it understands it.
- Add a `FR-P2`/`FR-P3` preview test (the serving logic exists and is untested).
- Translate the UI, or improve keyboard navigation and screen-reader labels.
- Reproduce a platform-specific bug on macOS or Windows and report it — CI only
  runs the full suite on Linux.

Say in the issue that you are picking it up so two people do not duplicate the
work.

## Governance

Consensus first, maintainer decides. In practice:

- The maintainer merges changes that pass CI, are in scope, and do not
  increase the maintenance burden without giving something back.
- Substantial changes — a new language, a second service, a licence change, a
  schema redesign — come with an ADR in `docs/adr/`. Copy an existing one.
- Dependabot may merge dev-dependency bumps. Runtime dependencies are a human
  decision, because a bump can be a breaking change.
- Two maintainers have not happened yet, so there is no succession plan. That is
  a real limitation of a project this size, and it is a reason to keep the
  architecture boring and the docs current.

## Licence

By contributing you agree your work is licensed under
[AGPL-3.0-only](LICENSE), the same as the project. That is a deliberate choice
(see [ADR-010](docs/adr/ADR-010-license.md)): if you host a modified LocalDrop
as a network service, you must offer your source to your users.

If your employer requires a different licence assignment, raise it **before**
you write the code, not after.
