# ADR-011 — Packaging, distribution and installation

* **Status:** Accepted
* **Date:** 2026-10-01
* **Deciders:** maintainer
* **Supersedes:** nothing. Extends [ADR-009](ADR-009-deployment.md), which
  settled the container deployment and deferred the native question.

## Context

1.0.0 shipped exactly one supported way to run LocalDrop: build the image from
the `docker-compose.yml` in the repository. That is a good way to run a server
*if* you have Docker, a git clone, and patience with a build.

It is not how people run a home server. It is not how you run anything on a
Raspberry Pi, on a NAS, on a company laptop, or on a machine where you are not
willing to install a container runtime. It is also not how a macOS or Windows
user thinks about installing an application, so 1.0.0 had effectively excluded
two of the three desktop platforms and most single-board hardware.

Three questions had to be answered before 1.1.0 could be called a release.

## Decision

### 1. The version lives in exactly one file

`backend/src/localdrop/__about__.py` is the single source of truth. The wheel
reads it dynamically through hatchling's `[tool.hatch.version]`, the launcher
reports it, `GET /api/v1/version` returns it, and the Settings panel displays
it. Release tooling substitutes it into the artefacts.

At 1.0.0 the version was written in six places and three of them disagreed
(`1.0.0` in the FastAPI metadata, the compose file, the Dockerfile and the
Settings panel; `1.1.0` in `pyproject.toml`; "unreleased" in the changelog).
That is not a typo waiting to happen, it is a fact about how humans work.

Two enforcement mechanisms, because a convention nobody checks is a convention
that decays:

- `scripts/check_version.py` fails CI on a literal version in a derived file,
  and on a mismatch between the changelog, `package.json` and `__about__.py`.
- No release artefact is published unless `localdrop --check` passes on it.

The *derived* set (compose, Dockerfile, formula, installers) is required to
contain no version literal at all. The *synced* set (changelog, `package.json`)
is required to match, because those formats demand a literal.

### 2. Native installs are a single self-contained binary

LocalDrop is frozen with **PyInstaller**, not written in Go or Rust, and not
distributed as a `pip install` that asks the user to provide a Python runtime.

Rejected, deliberately:

- **`pip install` as the primary path.** It makes "installing" a prerequisite
  job. A self-hosted tool that a non-admin can run in one command is worth more
  than the packaging elegance. `pip install` remains supported for people who
  already have Python 3.12 and want to patch the source.
- **Rewriting the server in Go or Rust.** The single-binary goal does not
  justify discarding a working, tested, security-reviewed implementation. A
  `localdrop` CLI client in a fast language remains a reasonable future
  (spec 08 §11); reimplementing the *server* is not.
- **Shipping the wheel inside the Docker image only.** That is what 1.0.0 did,
  and it is what left three platforms unsupported.

**PyInstaller cannot cross-compile.** This is the constraint that shapes the
release pipeline: each platform is built on a native runner. It is a real cost
(five jobs, ~20 minutes) and the alternative — a binary that is subtly broken
because it was cross-compiled — is worse.

**One bundle on Unix, one directory on Windows.** A onefile bundle is a single
self-extracting file, which is exactly what `curl | sh`, a tarball and the
Homebrew formula want, and a server that stays up does not care about a one
second start. A onefile *Windows* build unpacks to `%TEMP%` on every start,
which antivirus software flags and which makes the Inno Setup installer slow
and fragile. Windows therefore ships a directory tree: zipped for portable use,
wrapped by the installer for normal use.

### 3. The migrations and the web UI ship inside the package

`src/localdrop/migrations/` and `src/localdrop/static/` moved out of
`backend/`.

At 1.0.0 they sat next to the source, and the Dockerfile copied them back into
place next to the installed package. That worked for Docker and worked nowhere
else: `pip install localdrop` produced a server that could not migrate, and a
frozen build had to be told where to look. The launcher's `_bundled()` helper
was the seam that papered over it.

Inside the package, `launcher._bundled()` resolves one path for all four
install methods, and `migrate.py` builds its Alembic config programmatically so
no `alembic.ini` has to be found relative to the working directory.

`test_packaged_resources_exist_outside_a_frozen_build` is the guard.

### 4. A native install brings its own database

When `LOCALDROP_DATABASE_URL` is unset, the launcher provisions an embedded
PostgreSQL cluster inside the data directory.

This is the decision that most changes the character of the product. It means:

- a native install is one binary and one directory, with no second service to
  start, secure, back up or remember;
- backing up LocalDrop means backing up one folder;
- the "boring deployment" promise survives on a Raspberry Pi.

The cost is honest and worth stating: PostgreSQL binaries are downloaded from
Maven Central on first run and are **not** checksum-verified, which is weaker
than the treatment release artefacts get. Pinning and verifying them is
tracked, not done.

Anyone who already runs PostgreSQL sets one environment variable and the
embedded cluster is never touched. Docker does exactly that.

### 5. One service definition per platform, installed by the installer

- **Linux:** a systemd unit, a `localdrop` system account with no login shell,
  `/var/lib/localdrop`, config in `/etc/localdrop/localdrop.env`. Sandboxed with
  `NoNewPrivileges`, `ProtectSystem=strict` and `ReadWritePaths` narrowed to the
  data directory. There is also a `--no-service` mode for hosts without systemd.
- **macOS:** a launchd **LaunchAgent**, not a LaunchDaemon. Homebrew is
  strictly per-user and may not write outside its prefix, so a system-wide
  daemon is not something the formula can install. `localdrop
  install-service` sets it up; the user keeps the choice.
- **Windows:** Start Menu and desktop shortcuts, an optional start-at-login
  shortcut, and a real uninstaller. No Windows service: a server on a home
  desktop should start when you sign in, not fight you for a port at boot.

The launcher's `--data-dir` default remains per-user
(`%LOCALAPPDATA%\LocalDrop`, `~/Library/Application Support/LocalDrop`,
`$XDG_DATA_HOME/localdrop`) because "just run the binary" must work for whoever
typed the command. The service definitions set an explicit system-wide path
instead, which is the right default for a machine that runs one.

### 6. Docker is now pull-based, from a public registry

`docker-compose.yml` no longer has a `build:` section. It pulls
`ghcr.io/abhi-subedi/localdrop:${LOCALDROP_IMAGE_TAG:-stable}`.

Two reasons. At 1.0.0 the file referenced a locally built `localdrop:1.0.0`
tag, so the documented upgrade path — `docker compose pull && docker compose
up -d` — could not possibly work. And a `build:` section means every user
rebuilds the image, which is a slower and less reproducible first install than
pulling one. The image is still in the repository; `docker build -f
docker/Dockerfile .` still works, and the Dockerfile now takes its version as a
build argument rather than hard-coding it.

GHCR rather than Docker Hub: it is free, tied to the repository, and needs no
separate account. Tags are `:1.1.0`, `:1.1`, `:stable` and `:latest`, so a
user can pin a reproducible deploy or track the newest release.

## Consequences

**Good**

- Every platform the project claims to support is installable in one command,
  with a checksum verified before anything is unpacked.
- `docker compose pull` works, so the documented upgrade path is real.
- The version cannot drift, and cannot be published inconsistently.
- CI is green on its own gates, so a broken PR is visible before review.
- A maintainer can cut a release by tagging, with no manual steps.

**Bad, and accepted**

- Five native build jobs per release. PyInstaller does not let us avoid it.
- The release pipeline is the most complex thing in the repository. It is also
  the thing that has to be right on the one day it matters.
- Windows binaries are **unsigned**, so SmartScreen warns. Signing needs a
  certificate and a paid annual renewal; not done.
- macOS ships tarballs rather than bottles, because bottles need an Apple
  Silicon runner and a signed notarisation ticket. `brew install` therefore
  fetches a binary instead of using a pre-built bottle.
- The embedded PostgreSQL download is unverified (above).
- A user who upgrades across a major version has no rollback other than a
  restore. Migrations are forward-only, deliberately: automatic downgrades are
  how databases get corrupted.

**Neutral**

- The Docker image is now a build of the same source as the binaries, not a
  separate distribution channel. One artefact, five shapes.
- `pip install` still works, and is still the best path for someone who wants to
  read and modify the source.

## Alternatives rejected

| Option | Why not |
|---|---|
| Docker-only, 1.0.0's model | Excludes macOS, Windows and every device without a container runtime. |
| `pip install` as the primary path | Makes installing a prerequisite job; requires a Python runtime the user must already have at the right version. |
| Rewriting the server in Go | Discards a working, tested implementation for a packaging win. The transfer path is the security-critical core and is best left alone. |
| Distributing a `localtunnel`-style single static file per platform from 1.0.0's own tooling | PyInstaller needs a native runner per platform either way; no saving, less control over contents. |
| `uv` / `pex` instead of PyInstaller | Both are viable, but PyInstaller produces a directory Windows can ship in an installer and is already understood by the ecosystem. |
| Requiring an external PostgreSQL everywhere | Adds a second service to install, secure, back up and remember, for a single-owner LAN tool. Too much ceremony. |
| Signing Windows binaries now | Needs a purchased code-signing certificate. A note in the docs beats an expired certificate. |

## Links

- [ADR-009 — Deployment](ADR-009-deployment.md) — the container decision this extends
- [ADR-010 — Licence](ADR-010-license.md) — AGPL-3.0-only
- [`docs/spec/08-engineering.md` §6, §9](../spec/08-engineering.md) — CI/CD and
  release design this implements
- [`docs/spec/11-build-contract.md`](../spec/11-build-contract.md) — BC-9 (the SPA
  is a static build served by the backend)
