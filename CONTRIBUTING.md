# Contributing

Thanks for stopping by — LocalDrop is a small, boring-by-design codebase and
we'd like to keep it that way.

## Ground rules

1. **Small slices.** One user-visible behavior per PR (backend + frontend +
   tests). No drive-by refactors, no speculative frameworks.
2. **Tests are the spec.** Touching auth, storage, uploads, downloads, or
   sharing? Extend `backend/tests/test_v1_critical.py` in the same PR.
3. **Docs drift is a bug.** Changed behavior → update the matching guide in
   `docs/` (`docs/` is normative for users; `docs/spec/` for architecture).
4. **No new runtime dependency** without one paragraph in the PR explaining
   why the stdlib (or what's already vendored) can't do it.
5. **Security-sensitive areas** (auth, path handling, serving policy, share
   tokens): add a negative test (traversal corpus, oracle check, race) or
   say why you didn't.

## Workflow

```bash
git checkout -b feat/<short-name>
# … implement slice + tests + docs …
cd backend && python -m pytest tests/ -q
cd ../frontend && npm run build
```

PRs need: green tests, updated docs, no secrets in diffs. Architecture
changes (anything touching an ADR or the API contract) need a short written
proposal first — open an issue before the code.

## Good first issues

Look for `good-first-issue`: usually UI polish, extra hostile-name corpus
entries, docs gaps, or additional MIME sniff signatures.

## Conduct

Be kind and direct. [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies.
