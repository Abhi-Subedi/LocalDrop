# 08 — Engineering: Repository, Dev Environment, Config, Testing, CI/CD, Docker, Releases, Open Source

*Status: Proposed.*

---

## 1. Repository structure

Two runtimes, no shared packages in v1, contributors arrive for either side — so the
layout is **flat and boring by design**:

```text
localdrop/
├── backend/                    # FastAPI app (Python 3.12, uv-managed)
│   ├── src/localdrop/          #   layout per 03 §3.1
│   ├── migrations/             #   alembic
│   ├── pyproject.toml
│   └── tests/{unit,integration,security}
├── frontend/                   # React SPA (pnpm)
│   ├── src/                    #   layout per 07 §1
│   ├── package.json
│   └── tests/ (unit)           #   e2e lives in /e2e (shares fixtures)
├── e2e/                        # Playwright suites + adversarial corpora
├── docker/
│   ├── Dockerfile              # multi-stage: builder (node) → runtime (python-slim)
│   ├── docker-compose.yml      # production stack (app + postgres)
│   ├── docker-compose.dev.yml  # hot-reload dev stack
│   └── entrypoint.sh           # migrations + pre-flight checks
├── docs/                       # this specification; grows into user docs
├── scripts/                    # seed.py, backup.sh, restore.sh, release.sh
├── .github/
│   ├── workflows/              # ci.yml, release.yml, nightly-perf.yml
│   ├── ISSUE_TEMPLATE/         # bug.yml, feature.yml, config
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml
├── CHANGELOG.md · CONTRIBUTING.md · SECURITY.md · CODE_OF_CONDUCT.md · LICENSE
└── README.md
```

**Why not `apps/`+`packages/` monorepo tooling:** nothing is shared yet — the moment a
generated API client or shared validation rules exist (Phase 5, maybe Phase 2), the
layout can graduate to `apps/ + packages/` with git history preserved; paying
turborepo/pnpm-workspace complexity now buys nothing for a two-directory problem.
**Why e2e at root:** Playwright drives both stacks against real compose, and its
corpora are security artifacts (06 §2) — they belong to the repo, not to `frontend/`.

---

## 2. Development environment (clone → running)

**Native (preferred for iteration):** requires Docker (for Postgres), Python 3.12+
(via `uv`), Node 20+ / pnpm 9+.

```bash
git clone … && cd localdrop
cp .env.example .env                     # sane dev defaults
docker compose -f docker/docker-compose.dev.yml up -d postgres
make dev                                 # = backend: uv sync && uv run uvicorn … --reload
                                         # + frontend: pnpm install && pnpm dev
# first run: setup token printed in backend console → open http://localhost:5173/setup
make seed                                # test accounts + sample files (dev only)
```

- Dev mode: Vite dev server proxies `/api` to :8080 (HMR both sides); SPA auth works
  in either origin via cookie (`SameSite=Lax` is fine on localhost).
- **Test accounts (seeded):** `owner / owner-dev-password` (+ sample tree of 200
  files incl. adversarial names); wiped by `make reset`.
- No superuser credentials anywhere; Postgres runs with a random generated password
  persisted to `.pgdev.env` (gitignored).

**Full-docker alternative** (`docker compose -f docker/docker-compose.dev.yml up`):
backend + frontend containers with bind-mounts + reload; used to reproduce
"works in compose" bugs. CI runs the same file — one dev environment definition.

**Requirements summary** (also in `CONTRIBUTING.md`): git, Docker, uv, pnpm — four
tools, all one-liner installs; `make doctor` diagnoses the common breakages (ports in
use, stale venv, wrong node version).

---

## 3. Configuration

12-factor env-only (03 §9 has the table with defaults; `config.py` is the single
source of truth and CI-doc-sync keeps this table honest). Classification:

- **Required (production):** `LOCALDROP_DATABASE_URL`, `LOCALDROP_SECRET_KEY`.
- **Optional with safe defaults:** everything else (storage dir, limits, TTLs, rate
  classes, logging, mDNS).
- **Development-only:** `LOCALDROP_DEV_MODE` (permissive CORS for :5173, dev log
  format, seed helpers exposed). The production compose file never sets it; docs
  warn loudly that it disables security conveniences and must never be used on a
  reachable network.
- **Production checklist** (docs page): secret key from a password manager (≥ 32
  chars), `PUBLIC_URL` when behind proxy, TLS via reverse proxy, volume for
  `DATA_DIR`, backups wired (§7).

**Secrets handling:** env-file (0600) or docker secrets; startup logs a **redacted**
config dump (keys shown, values masked except non-secrets); `SECRET_KEY` rotation
documented (sessions + PAT hashes are HMAC'd with it → rotation invalidates all
sessions — feature, not bug).

---

## 4. Observability

- **Logs:** structlog JSON to stdout — `ts, level, request_id, principal, route,
  status, duration_ms, bytes_in/out, event`; jobs log their own spans. `dev` format
  is colored key=value. Log levels: `debug` (chunk appends — off by default), `info`
  (lifecycle, mutations), `warning` (rate-limit hits, GC anomalies, storage
  pressure), `error` (5xx, job failures). PII discipline per 06 §2.15.
- **Health:** `/health/live` (process), `/health/ready` (DB roundtrip + storage
  writable + migration head) — wired to compose healthchecks and documented for
  uptime-kuma-class monitors.
- **Metrics:** `prometheus-client`, `/metrics` (PAT `metrics` scope):
  `http_requests_total{route,status}`, `http_request_duration_seconds`,
  `upload_sessions_active`, `upload_bytes_total`, `download_bytes_total`,
  `storage_bytes`, `blob_gc_reclaimed_bytes`, `job_duration_seconds{job}`. Intentionally
  ~10 metrics; this is a home-server product, not a SaaS control plane.
- **Error reporting:** none external (privacy rule). Errors are logged with
  request_id; the UI shows the id so users can grep their own logs. An *opt-in*
  local "export diagnostics bundle" command (sanitized logs + config dump +
  versions) is Phase 4.

---

## 5. Testing strategy

| Level | Tool | Scope | CI |
|---|---|---|---|
| L1 unit | pytest + hypothesis | services' pure logic: name validation, offset arithmetic, rate limiter, share validity windows, path derivation; frontend: vitest + testing-library for primitives | every PR |
| L2 integration | pytest + httpx AsyncClient + real Postgres (service container) + tmp data dir | **the money suite**: tus lifecycle (create/append/interrupt/resume/finalize/dedup), download ranges/ETag, share flows (expiry/limit/password), trash/GC, session lifecycle, SSE events | every PR |
| L3 E2E | Playwright vs. compose stack | golden flows: onboarding→login→upload(big fixture 2 GB sparse)→browse→preview→share (with password)→download as fresh anonymous context→revoke→404; mobile viewport run of the same | PR (linux), plus windows/macos nightly |
| L4 security | pytest parametrized corpora + generated authz matrix | everything in 06 §5 checklist | every PR |
| L5 performance | custom harness in `e2e/perf/` | NFR-1/2/3/4: 20 GB upload RAM-capped, throughput, 20 concurrent sessions, range-resume correctness | nightly on self-hosted runner; numbers posted to PR as artifacts |

**Build order (what gets tested first):** L2 upload lifecycle and L4 name/traversal
corpora **before** the SPA exists (backend usable via curl), then authz matrix, then
E2E golden flow, then perf harness. Rationale: the transfer path and the attack
surface are the two irreducible cores; everything else is recoverable.

Coverage target: services/ and storage/ ≥ 90 % line; routers ≥ 80 %; no global
number-worship — the gate is "every FR-M has a test referencing its id" (traceability
enforced by a tiny CI script grepping FR ids in test names).

---

## 6. CI/CD (GitHub Actions)

**`ci.yml` (PR + main):** jobs — `backend` (ruff lint+format, mypy strict, pytest
L1/L2/L4 w/ postgres service), `frontend` (eslint, tsc, vitest, build), `e2e`
(compose up → Playwright, needs the two above), `docker-build` (build only, no push),
`openapi-freeze` (diff generated OpenAPI vs. committed spec), `docs-sync` (config
table vs. config.py). Total wall-clock target < 15 min on GitHub runners.

**`release.yml` (tag `v*`):** test suite → `docker/buildx` multi-arch (amd64+arm64)
→ push `ghcr.io/localdrop/localdrop:{tag}` + `:stable` + `:_major` → SBOM (syft)
attached → GitHub Release from CHANGELOG + compose file attached → sign with cosign
`[Phase 4]`.

**`nightly.yml`:** L5 perf + windows/mac E2E + trivy image scan + pip-audit/pnpm
audit → issue auto-filed on regression.

**Practicality rules:** no matrix spam (python/node single versions, the ones in the
containers), concurrency-cancel on PR force-push, cache pip/pnpm/store via actions
cache. Dependabot: weekly, grouped by ecosystem, auto-merge devDeps only.

---

## 7. Docker architecture (conceptual — implementation deferred)

Two services; **no nginx container** *(ADR-009 — the app serves the SPA and streams
fine itself; a proxy is the deployer's perimeter choice)*:

```text
┌────────────────────────── host ─────────────────────────┐
│  ┌─ localdrop ──────────────┐   ┌─ postgres:16 ──────┐  │
│  │ image: ghcr.io/localdrop │   │ internal net only  │  │
│  │ user: 1000 (non-root)    │◄──┤ random pw in local │  │
│  │ ro rootfs, caps dropped  │db │ volume: pgdata     │  │
│  │ :8080 → host 8080        │   └────────────────────┘  │
│  │ volume: localdrop-data   │                           │
│  │  → /data (blobs+staging) │   healthchecks:           │
│  │ entrypoint: migrate→serve│    app: /health/ready     │
│  └──────────────────────────┘    db: pg_isready         │
│  network: localdrop-internal (bridge)                   │
└─────────────────────────────────────────────────────────┘
```

Upgrade path = `docker compose pull && docker compose up -d` (entrypoint migrates,
with `pg_dump` safety valve per 04 §6). Reverse-proxy snippets (Caddy, Traefik,
nginx, tailscale) are docs pages with copy-paste configs incl. SSE-friendly
settings (`proxy_read_timeout 3600s; proxy_buffering off` for `/api/v1/events`).

---

## 8. Backup & recovery (documented, tested)

- **What:** `pg_dump` (metadata) + `data/` (blobs — content-addressed, so it's
  rsnapshot/rsync-friendly: unchanged blobs are stable filenames).
- **Bundled:** `scripts/backup.sh` (stop-free: pg_dump + rsync with
  `--link-dest` snapshots) and `scripts/restore.sh` (verify dump, restore DB,
  verify blob tree against DB reconciliation query, boot).
- **Restore drill** is a CI job (nightly): nuke stack → restore last nightly's
  fixture backup → health + sample download verified. A backup story without a
  restore test is a rumor.

---

## 9. Versioning, upgrades, releases

- **SemVer.** `0.x` during MVP development (API may shift, images tagged `:0.x`);
  `1.0.0` at first public release = the stability promises of NFR-15 begin.
- **Breaking change = major** (API removals, env rename, compose shape change,
  storage layout change). DB migrations never auto-run across a major without the
  safety-valve backup.
- **Downgrades:** unsupported (forward-only migrations); recovery = restore backup.
  Docs state this loudly at the top of the upgrade page.
- **Release cadence:** patch as-needed; minor ~monthly train; CHANGELOG
  keep-a-changelog format, human-written summaries + auto-linked PRs.
- **Upgrade process (user-facing):** backup → `pull` → `up -d` → watch migration
  log → check `/health/ready`. Documented rollback = restore.

---

## 10. Open-source strategy

- **License:** **AGPL-3.0** recommended — tradeoffs analyzed in
  [ADR-010](../adr/ADR-010-license.md) (adoption-maximizing MIT vs.
  hosted-fork-protecting AGPL; Apache-2.0 middle ground rejected for lacking the
  network-use clause). **[DECISION REQUIRED: maintainer ratification]** — the only
  license question that genuinely needs the founder.
- **Community files (in repo from Phase 0):**
  - `CONTRIBUTING.md` — dev env (§2), code style, PR checklist (tests + docs +
    threat-model impact if touching auth/storage), "good first issue" ladder.
  - `CODE_OF_CONDUCT.md` — Contributor Covenant, enforcement contact.
  - `SECURITY.md` — private reporting (GitHub advisories), supported = latest
    minor, response SLA 7 d, no-auto-CVE-bot note.
  - Issue templates: bug (env, version, compose, logs with redaction reminder),
    feature (use-case-first, not solution-first).
  - `SUPPORT.md` — discussions vs. issues routing.
- **Governance (light):** maintainer + triage role documented; consensus-first,
  maintainer-decides; CONTRIBUTING states it plainly.
- **Roadmap** public (02 §4) with phase status — feature requests are triaged
  against it, not against maintainer energy.

---

## 11. CLI (future design — do not build)

`localdrop` (Rust or Go single binary — `[DECISION REQUIRED Phase 5]`; Python
excluded: users shouldn't need a runtime) against the same REST API:

```text
localdrop login <url>            # opens browser for PAT grant flow
localdrop upload <file>… [--to FOLDER]   # tus client, progress, resume
localdrop download <name|id> [-o out]    # ranged GET, resume
localdrop share <file> [--days 7] [--password]   # prints URL+QR
localdrop ls / tree / rm / mv
localdrop status                 # server health, storage, sessions
```

Same PAT scopes as the API (05); zero special server endpoints beyond a token-grant
handshake `[Phase 5 design]`.

---

*Next: [09 — Diagrams](09-diagrams.md).*
