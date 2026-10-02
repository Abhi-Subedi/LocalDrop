# Changelog

All notable changes to LocalDrop are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) ·
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The canonical version lives in
[`backend/src/localdrop/__about__.py`](backend/src/localdrop/__about__.py); this
file is checked against it by `scripts/check_version.py`.

## [Unreleased]

Nothing yet.

## [1.1.2] — 2026-10-02

**Two packaging faults made the released binaries unusable.** Both passed CI,
passed `localdrop --check`, and were only found by installing the published
artefact and opening it. 1.1.1 was withdrawn within minutes of publication for
the first of them.

### Fixed

- **The web UI was never served.** The SPA directory had two resolvers:
  `launcher._bundled()` used `sys._MEIPASS`, while `main.SPA_DIST` used
  `Path(__file__).parent / "static"`. PyInstaller points `__file__` at
  `<bundle>/localdrop/main.py`, so the second looked in
  `<bundle>/localdrop/static` while the files ship in `<bundle>/static`.
  `SPA_DIST.exists()` was therefore always False in a frozen build, so the
  catch-all route and the `/assets` mount were never registered:
  `GET /api/v1/version` returned 200 and `GET /` returned 404. `if
  spa.exists()` made it silent. `--check` missed it precisely because it
  already used the correct resolver. Both callers now share one implementation
  in `localdrop/paths.py`, and a missing SPA logs an error at startup instead of
  quietly degrading to 404s.
- **The Windows archive dropped the whole PyInstaller payload.** The archive walk
  was gated on `exe.is_dir()`, which is never true because `exe` is a file in
  both build modes, so `_internal/` was omitted and the binary died with
  `Failed to load Python DLL .../_internal/python312.dll`. The published zip had
  3 entries where it should have had 803.

### Added

- Regression tests for both, in the shape that failed: one builds a fake
  `<bundle>` and asserts `main.SPA_DIST` finds the real `index.html`, the other
  builds a one-directory payload and asserts the archive contains it. Both were
  verified to fail against the code that shipped.

## [1.1.1] — 2026-10-02 (withdrawn)

> **Withdrawn shortly after publication.** The Windows archive was missing
> its PyInstaller payload (#31), and on every platform the binary could not
> serve the web UI (#32). Use 1.1.2. The fixes below - the installers, the
> embedded PostgreSQL and Homebrew - are all still in force.


**Every install path was broken in the same way, and Windows could not start at
all.** The one-liner installers advertised in the README resolved the release
version from `raw.githubusercontent.com/<owner>/<repo>/VERSION`, which is a URL
that cannot exist — the CDN needs a ref in the path. So `irm ... | iex` and
`curl ... | sh` failed for every user on the default path, on every platform,
and only worked if you happened to pass an explicit version. Fixing that
surfaced four more defects behind it, including one that made a completed
Windows install unable to start.

### Fixed

- **Both native installers failed to resolve a version** (`install.ps1`,
  `install.sh`). The URL was missing the `/main` ref, so it 404'd and the
  default `stable` path never worked. Resolution now reads the releases API
  first — where `latest` cannot name a version whose assets are missing — and
  falls back to `VERSION` on `main`, because depending on a single host is the
  underlying problem. `GITHUB_TOKEN` is honoured to lift the 60/hour API limit.
  A failure now names both URLs tried and how to pin a version, instead of a
  bare `404`.
- **A native Windows install completed and then could not start.** The embedded
  PostgreSQL was unpacked with `filter="tar"`, which reproduces the archive's
  `0o700` directory modes; on Windows that produces a *protected* DACL granting
  only `OWNER RIGHTS`, `SYSTEM` and `Administrators`, excluding the installing
  user. 73 of 76 extracted directories were affected, so `initdb` failed with
  `could not access file ".../pg/share/postgres.bki": Permission denied`.
  `localdrop --check` passed because it never touches the database. Now uses
  `filter="data"`, which is also the safer filter.
- **`brew install` could not have worked.** The advertised tap did not exist,
  and the formula did `pkgshare.install "LICENSE"` / `"README.md"` for files
  the tarballs never contained, which aborts the install. The tap is published
  at [`Abhi-Subedi/homebrew-localdrop`](https://github.com/Abhi-Subedi/homebrew-localdrop)
  and keeps itself current daily.
- **`linux-armv7` was accepted but has never been built.** `install.sh` requested
  an artefact no release publishes, so 32-bit ARM boards failed later with an
  unexplained download `404`. `build-binary.py` was worse: it fell through to
  labelling an armv7 build as `linux-x64`. LocalDrop ships 64-bit only.
- **`update-brew-formula.py --check-only` could never succeed.** It validated
  `--sha256-*` and then discarded them, so it always exited 2 before checking
  anything, which is why the placeholder check was wrapped in `|| true` and
  never fired.
- **The Homebrew formula could not be re-versioned.** `render()` only replaced
  placeholders, which are gone after the first release, so the formula stayed
  pinned to whatever version it first reached.

### Security

- The SPA catch-all route joins the request path onto the SPA directory, which
  is not safe on its own: on pathlib `base / "/abs"` discards `base` entirely,
  and a bare absolute path resolves to a real file outside the SPA. The
  `is_relative_to` guard is correct and is now pinned by a test that fails when
  the guard is removed. The three CodeQL `py/path-injection` alerts on this
  function are answered by that test rather than dismissed on inspection.

### Added

- LICENSE and README.md ship inside the release archives. AGPL-3.0 requires
  conveying the licence with the binary, so this closes a compliance gap as well
  as a packaging one.
- `GOVERNANCE.md`, stating the project's scope and decision-making plainly.
- A pinned roadmap issue listing what still needs building, and what will not.
- Discussions, with a "start here" post.
- CodeQL analysis for Python, JavaScript/TypeScript, Ruby and Actions.

## [1.1.0] — 2026-10-01

**LocalDrop is now installable on every platform.** 1.0.0 shipped a Docker-only
install that worked, but left a Linux server, a Mac, and a Windows desktop with
three different un-documented workarounds. This release closes that gap and makes
the repository releaseable as open source.

### Added — installation

- **One-line Linux/macOS installer.** `curl -fsSL …/install.sh | sh` downloads a
  checksummed binary, verifies its SHA-256, creates a locked `localdrop` system
  account, installs a systemd unit (Linux) or a launchd job (macOS), generates a
  secret key, and starts the service. `--no-service` installs the binary alone;
  your data and config are never overwritten.
- **Windows installer.** A proper Inno Setup package (Start Menu and desktop
  shortcuts, optional start-at-login, uninstaller) plus a portable zip of the
  same payload. Both are checksummed.
- **`install.ps1`** for Windows: fetches, verifies, installs, and runs
  `localdrop --check` to prove the install works before it reports success.
- **Homebrew formula** for macOS (`brew install abhi-subedi/localdrop`) —
  per-user, no `sudo`, no service auto-install.
- **`uninstall.sh`** that keeps your data by default and only deletes it when
  you pass `--purge` and confirm.
- **Self-contained installs need no database at all.** When
  `LOCALDROP_DATABASE_URL` is unset, the launcher provisions an embedded
  PostgreSQL inside the data directory, so a native install is a single binary
  with nothing else to install. Point it at your own PostgreSQL and the
  embedded cluster is never started.
- **Frozen binaries for every platform** — `linux-x64`, `linux-arm64`,
  `macos-x64`, `macos-arm64`, `windows-x64` — with a published `SHA256SUMS`.
- **Published container image** on `ghcr.io/abhi-subedi/localdrop` for
  `linux/amd64` and `linux/arm64`, tagged `:1.1.0`, `:1.1`, `:stable`,
  `:latest`, with OCI labels and provenance attestation.

### Added — operating the server

- **`localdrop --check`** verifies an install is self-sufficient and exits: every
  bundled resource, the heavy C extensions (psycopg, argon2, Pillow) and the app
  factory. It needs no database, so it works when the thing that is broken *is*
  the database. The release pipeline runs it against every artefact before
  publishing.
- **`localdrop --setup-token`** prints the one-time onboarding token on demand,
  so a headless install does not have to dig it out of `journalctl`.
- **`localdrop install-service` / `uninstall-service` / `service-status`** for a
  per-user macOS LaunchAgent — the launchd job Homebrew users need, since
  Homebrew will not install one for them.
- **`localdrop-migrate`** applies migrations programmatically, so the packaged
  Alembic environment is found regardless of working directory. Docker, systemd,
  the launcher and the frozen binary all use the same path.
- **`localdrop.env`** is read from the data directory when present, so every
  platform is configured the same way. Real environment variables still win.
- **`GET /api/v1/version`** reports the running build (public, and free of any
  deployment detail). The Settings "About" panel reads it instead of showing a
  hard-coded string.
- **`/api/v1/health/ready`** reports the failing subsystem by name, and
  `LOCALDROP_DB_CONNECT_TIMEOUT` / `LOCALDROP_DB_KEEPALIVE_SECONDS` bound how
  long it can take to find out.

### Added — working on the project

- **Continuous integration** (`.github/workflows/ci.yml`): lint, types, the
  test suite against real PostgreSQL 16, a frontend type-check and build, a
  frozen-binary build that self-checks, and a Docker build that must serve
  `/api/v1/version`.
- **Automated releases** (`release.yml`): tag a version and get binaries for
  five platforms, a multi-arch image, checksums, a Release whose notes come
  from this file, an updated `VERSION` file, and a pushed Homebrew formula.
- **Nightly checks** (`nightly.yml`): `pip-audit`, `npm audit`, a Trivy scan of
  the published image, CodeQL, and an end-to-end pass against the real
  `stable` image that fails if it is not the version `VERSION` claims.
- **Dependabot**, grouped by ecosystem so review is a handful of PRs, not
  dozens.
- **`scripts/check_version.py`**, **`scripts/check_config_docs.py`** and
  **`scripts/check_fr_traceability.py`** — the doc-drift gates the spec asked
  for and never had. Requirement-to-test traceability is now enforced, with the
  remaining gaps registered and visible instead of assumed.
- **`SECURITY.md`**, **`SUPPORT.md`**, bug and feature issue templates, a PR
  template, `CODEOWNERS`, `.editorconfig` and `.gitattributes`.

### Fixed

- **Readiness took 130 seconds to report a dead database.** The engine had no
  `connect_timeout`, so libpq waited its default ~2 minutes — longer than the
  Docker healthcheck's 5-second timeout. Now ~5 seconds, with a regression test
  that fails if the bound is removed.
- **Pool hygiene:** `pool_recycle` and `pool_timeout` are set, and TCP keepalives
  close half-open connections instead of letting them pin a pool slot.
- **Production builds shipped without any CSS.** `index.css` was never imported
  by the app entry, so the built SPA rendered unstyled.
- **A pip install could not run.** The migrations and the built web UI lived
  outside the package, so only the Docker layout — which copied them back in by
  hand — worked. Both now ship inside the wheel, and `pip install localdrop`
  and the frozen binary resolve them identically.
- **`docker compose pull` could not work.** The compose file referenced a
  locally built tag that was never published. It now pulls from GHCR, so the
  documented upgrade path is real.

### Changed

- **One version, one source of truth.** `__version__` in
  `__about__.py` feeds the wheel, the binary, the HTTP API, the Settings panel
  and the release tooling. The three-way drift between `1.0.0`, `1.1.0` and
  "unreleased" is no longer possible; CI fails if it comes back.
- **The repository's own quality gates now pass.** `ruff` and `mypy` were
  reporting 230 and 37 problems respectively before this release. Both are clean.
- **`docs/CONFIGURATION.md` is complete** — it was missing 15 settings.

### Security

- Release artefacts are SHA-256 verified by every installer before anything is
  unpacked, and releases carry a provenance attestation.
- The systemd unit runs as a dedicated account with `NoNewPrivileges`,
  `ProtectSystem=strict` and `ReadWritePaths` limited to the data directory.
- Windows and macOS installs write the config file `0600`; the launchd plist
  holds the secret key and is not world-readable.
- Reports go through private vulnerability reporting, not public issues.

### Known limitations

- Single owner account; no multi-user sharing (use public links).
- Files live in folders; no folder or zip download.
- No live cross-device refresh (no SSE): the UI refreshes after your own
  actions, and another device's changes appear on reload.
- LAN discovery is URL + QR. `LOCALDROP_MDNS_ENABLED` is reserved and unused.
- macOS Homebrew ships raw tarballs, not bottles: no `brew install` of a
  pre-built binary, so the formula builds from the release archive.
- Windows binaries are unsigned. SmartScreen will warn on first run.
- 9 of 31 Must-have requirements have no automated test; they are listed with
  reasons in `scripts/check_fr_traceability.py` under `KNOWN_GAPS`.
- The embedded PostgreSQL is downloaded from Maven Central on first run and is
  not checksum-verified. (Release artefacts are; this one is not yet.)

## [1.0.0] — 2026-10-01

First usable release: a single-owner, self-hosted file drop box.

### Added

- **Auth:** first-run setup token (console + `/setup/token`, last-writer-wins),
  owner onboarding, login/logout, DB sessions (idle 7 d + absolute 30 d,
  rotation, per-device list/revoke), password change (revokes others), personal
  access tokens (`read|write` scopes), login rate limiting with lockout.
- **Files:** folders (create/rename/move incl. top level/delete/restore,
  cycle guard, case-insensitive collisions), file rename/move/copy/delete,
  trash with restore + purge, search, six sort orders, paginated listings.
- **Uploads:** native tus 1.0.0 subset (create/offset/append/cancel), per-chunk
  sha256, interrupt + HEAD resume, streaming bounded-RAM writes, dedup by
  content hash, `O_BINARY`-safe byte handling on all platforms.
- **Downloads:** streaming, single-range resume (`206`), suffix ranges,
  `ETag`/`If-Range`, magic-byte sniffing with an inline/attachment policy
  (SVG/HTML/XML always download, never render).
- **Sharing:** 26-char secure tokens, expiry, download limits (atomic,
  race-free), passwords (argon2id + HMAC cookie), revocation, QR codes,
  anonymous `/s/{token}` page, indistinguishable 404s for dead links.
- **UI:** React SPA — file browser (breadcrumbs, drag-drop, selection,
  context menus, previews, upload sheet with progress), shares manager,
  trash, settings (password, sessions, PATs), public share page;
  mobile-first, keyboard accessible, dark-mode aware.
- **Deploy:** multi-stage Docker image (non-root, `cap_drop ALL`,
  healthchecks), 2-service Compose stack, entrypoint with DB wait +
  pre-migration `pg_dump` valve + auto-migrate, `backup.sh`/`restore.sh`.
- **Docs:** README, INSTALLATION, CONFIGURATION, BACKUP, SECURITY, API,
  DEVELOPMENT, CONTRIBUTING, Code of Conduct.
- **Tests:** 20-test critical-path suite (auth, authz isolation, file +
  share lifecycles, tus failure modes, hostile names, binary byte-identity).

### Security

- See `docs/SECURITY.md` for the threat model and hardening checklist.
- Serve past your LAN only over HTTPS; complete setup immediately.

### Known limitations (V1)

- Single owner account; no multi-user sharing (use public links).
- Files live in folders (no top-level files); no folder/zip download.
- No live cross-device refresh yet (no SSE): the UI refreshes after your own
  actions; another device's changes appear on reload. SSE arrives in v1.1.
- LAN discovery is URL + QR (no mDNS advertisement yet).

---

`0.x` versions covered MVP development. The API-stability promises of
`docs/spec/08-engineering.md` §9 begin at `1.0.0`.

Licensed under **AGPL-3.0-only** (ADR-010, ratified 2026-10-01).
