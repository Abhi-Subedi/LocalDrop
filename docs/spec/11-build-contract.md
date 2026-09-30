# 11 — Final Recommended Architecture & Build Contract

*Status: **Proposed — awaiting review approval.** Implementation of any kind must not
begin until this document is approved. Once approved, the items in §3 are binding on
all future implementation work (including agent-generated code); changing any of them
requires a new or amended ADR.*

---

## 1. Final recommended architecture (one screen)

```text
┌──────────────────────── localdrop (docker) ────────────────────────┐
│  FastAPI (Python 3.12) · single process · uvicorn                  │
│  ├── REST /api/v1  (OpenAPI 3.1 auto-generated; problem+json)      │
│  ├── tus-subset uploads → content-addressed blob store             │
│  ├── streaming downloads (Range/ETag, bounded RAM)                 │
│  ├── SSE /events   · in-process job scheduler (hash/thumbs/GC)     │
│  └── serves built React/Vite SPA (static, fingerprinted)           │
│        │ SQLAlchemy 2.0 + Alembic          │ /data volume          │
└────────┼────────────────────────────────────┼──────────────────────┘
    ┌────▼─────────┐                    ┌─────▼──────────┐
    │ PostgreSQL 16│                    │ blobs/ staging/ │
    └──────────────┘                    │ thumbs/         │
                                        └────────────────┘
```

**Stack:** FastAPI · SQLAlchemy/Alembic · PostgreSQL 16 · React 18 + TypeScript +
Vite + TanStack Router/Query + Tailwind + Radix · tus 1.0.0 subset · SSE · Docker
Compose (2 containers) · GitHub Actions · Playwright/pytest · AGPL-3.0 *(pending D1)*.

**Deliberately absent in v1:** Redis, message queue, microservices, nginx container,
Node server in production, S3 driver, plugin runtime, multi-worker scale-out.

---

## 2. Approval gates before any implementation

1. Maintainer approves this specification (ideally raising issues on `docs/`, not
   silently diverging while building).
2. **D1 (license)** resolved — the repo cannot be published without it.
3. Phase 1 spike list (10 §1, V1–V8) scheduled *inside* Phase 1, not after.

---

## 3. THE BUILD CONTRACT — binding decisions

Any contribution (human or agent) that contradicts a clause below is wrong until an
ADR amends it.

### Architecture invariants

- **BC-1** Single FastAPI process serves API, SPA, SSE, and runs the job scheduler.
  No sidecar services beyond PostgreSQL. (ADR-001/003/009)
- **BC-2** PostgreSQL is the only supported database in v1; schema changes go through
  Alembic migrations, forward-only, auto-run by the entrypoint with the pre-migrate
  `pg_dump` safety valve. (ADR-002)
- **BC-3** The filesystem is a **content-addressed blob store only**: paths built
  exclusively from server-generated UUIDs and hex hashes; **no user-supplied string
  ever reaches a filesystem path**. Layout per 03 §4.1. (ADR-004)
- **BC-4** All file-tree structure (folders, names, hierarchy) lives **in the
  database**; disk never mirrors it.
- **BC-5** Uploads implement the **tus 1.0.0 subset** per 03 §5.1 (POST/HEAD/PATCH/
  DELETE, offset semantics, `Upload-Checksum: sha256`, expiration). No bespoke
  chunk protocol. (ADR-005)
- **BC-6** **RAM is bounded regardless of file size**: request/response bodies stream
  (64 KiB–1 MiB buffers); hashing and image work run off the event loop in a bounded
  pool (≤ 2 workers). No code path may read a whole file into memory. (NFR-3)
- **BC-7** Mutations follow **storage-first, DB-second** ordering with GC-compensatable
  orphans (03 §5.5). Finalize is atomic (fsync → rename → commit).
- **BC-8** Realtime is **SSE** at `/api/v1/events`; clients must treat it as an
  optimization with polling fallback. No WebSocket. (ADR-006)
- **BC-9** The SPA is a **static build served by the backend**; no Node runtime in
  production; no third-party asset requests at runtime (offline rule). (ADR-008)

### Security invariants (from 06 — all non-negotiable)

- **BC-10** Authorization is **object-level, in services**, via standardized
  owned-fetch functions; route auth alone is never sufficient. New endpoints must
  join the generated authz test matrix.
- **BC-11** Names (files/folders/uploads) pass the single `NameStr` validation
  (NFC, no `/ \ NUL` or control chars, no leading/trailing dot/space, ≤ 255 bytes,
  bidi/zero-width stripped) **at the schema layer, everywhere, with no exceptions**.
- **BC-12** Content serving follows the **policy table in 06 §4** verbatim: sniffed
  type wins; SVG/HTML always `attachment`; `nosniff` everywhere; sandbox CSP on
  inline content.
- **BC-13** Sessions are opaque, DB-stored **hashed**; cookies HttpOnly/SameSite=Lax/
  Secure-on-TLS; unsafe methods require the `X-Requested-With` header under cookie
  auth; password hashing is argon2id.
- **BC-14** Share tokens carry 130 bits of CSPRNG entropy; validity states are
  indistinguishable to non-holders; unlock attempts have progressive backoff.
- **BC-15** **Zero outbound network calls at runtime** — enforced by the egress test;
  any future outbound feature requires a new ADR.
- **BC-16** Container: non-root uid 1000, read-only rootfs, `cap_drop: ALL`,
  `no-new-privileges`, no docker socket, no host mounts except the data volume
  (opt-in mDNS host-network profile is the sole documented exception).
- **BC-17** Rate limits are on by default with the 05 §1.1 classes; proxy-trust is
  opt-in via `LOCALDROP_TRUSTED_PROXIES`; IPv6 keys bucket at /64.

### Product invariants

- **BC-18** The web UI consumes **only** the public versioned REST API — no
  UI-exclusive endpoints, no hidden internals. (P8)
- **BC-19** Telemetry of any kind is prohibited; the privacy data table (06 §6) is
  exhaustive and CI-enforced against schema drift.
- **BC-20** MVP scope is frozen at 02 §5. Phase-gated features may be *designed for*
  (schema columns, seams) but **must not be implemented early**.

### Process invariants

- **BC-21** Every M-priority FR ships with a test referencing its FR id; L4 security
  suites run on every PR; release gates 02 §5 + 06 §5 block v1.0.
- **BC-22** Every new third-party dependency (runtime) requires justification in the
  PR that a maintainer can later read as an ADR-grade reason.
- **BC-23** Docs drift is CI-detected: OpenAPI freeze diff + config-table sync.
- **BC-24** `[NEEDS VALIDATION]` items touching MVP features must be resolved before
  the features they gate ship (mapping in 10 §1).

---

## 4. What "done" means (Phase 1 exit, restated)

Every M requirement in 02 §2 has a passing test; V1–V8 spikes resolved and their
answers folded back into docs; security checklist (06 §5) fully green; WCAG AA
audit passed on core pages; fresh-machine install rehearsal (two platforms) done
from docs alone; both-arch images on ghcr; backup-restore drill green in CI.
Then — and only then — tag `v1.0.0`.

---

*This concludes the Master Specification. Review order suggestion: this document →
ADRs → 06 security → 03 architecture, raising issues against `docs/`.*
