<!--
  Keep this short. A reviewer should be able to check each box in a minute.
  Anything the CI already enforces (lint, types, tests) does not belong here.
-->

## What this changes

<!-- What does this do, and why? Link the issue it closes. -->

Closes #

## How it was verified

<!-- Not "tests pass" - what did you actually check, and how? -->

- [ ] I ran it (describe: `docker compose up` / the binary / pytest)
- [ ] Backend: `cd backend && ruff check . && mypy src && python -m pytest tests/ -q`
- [ ] Frontend: `cd frontend && npm run lint && npm run typecheck && npm run build`
- [ ] Docs updated if behaviour or configuration changed

## Risk

- [ ] Backend only, no migration
- [ ] Adds or changes a database migration (forward-only; include the downgrade note)
- [ ] Touches auth, sessions, share tokens, or file paths — **say so here**
- [ ] Touches the storage layout, or anything on disk a user already has
- [ ] Changes an environment variable, a compose shape, or a public API
- [ ] Changes a release artefact: `packaging/`, `install.sh`, `install.ps1`, the systemd unit, the Inno Setup script, the Homebrew formula, `docker/`
- [ ] None of the above

## Checklist

- [ ] Tests cover the new behaviour, and a bug fix comes with a test that fails without it
- [ ] New tests are not skipped, `xfail`-ed, or weakened to make them pass
- [ ] No secrets, tokens, real file names or personal data in the diff
- [ ] New functional requirements are claimed in a test by naming the `FR-xN` id
      (see `scripts/check_fr_traceability.py`)
- [ ] User-facing changes are in `CHANGELOG.md` under `[Unreleased]`
- [ ] Commit messages explain *why*, not just *what*

<!--
  If you touch auth, storage or uploads, also consider whether
  docs/SECURITY.md needs a note. If you add a setting, add it to
  docs/CONFIGURATION.md - CI will fail otherwise.
-->
