# 03 — Architecture & Technology Evaluation

*Status: Proposed unless marked. Every major choice here has a companion ADR with the
full alternatives analysis. This document explains the **shape of the system**; the
ADRs explain **why it is that shape**.*

---

## 1. System overview

One application process, one database, one disk. That is the whole system.

```text
                        ┌──────────────────────────────────────────────┐
                        │  localdrop container (FastAPI, single process)│
  Browser / ──HTTP──▶   │  ┌────────────┐ ┌──────────┐ ┌────────────┐  │
  phone / CLI           │  │ REST API   │ │ static   │ │ background │  │
                        │  │ (auth,     │ │ SPA      │ │ scheduler  │  │
                        │  │ upload,    │ │ serving  │ │ (thumbs,   │  │
                        │  │ download)  │ │          │ │ GC, jobs)  │  │
                        │  └─────┬──────┘ └──────────┘ └─────┬──────┘  │
                        │        │            SSE             │         │
                        │  ┌─────▼────────────────────────────▼──────┐ │
                        │  │ core domain: files · blobs · shares ·   │ │
                        │  │ sessions · audit  (SQLAlchemy, typed)   │ │
                        │  └─────┬───────────────────────┬───────────┘ │
                        └────────┼───────────────────────┼─────────────┘
                          ┌──────▼──────┐         ┌──────▼──────────┐
                          │ PostgreSQL  │         │ /var/lib/       │
                          │ (container) │         │ localdrop/data  │
                          │ metadata    │         │ content blobs   │
                          └─────────────┘         └─────────────────┘
```

Invariants of the shape:

- **The database is the source of truth for structure** (folders, names, permissions,
  shares). **The filesystem is only a blob store** (content-addressed; meaningless
  without the DB). This split is what makes renames atomic, moves O(1), path traversal
  structurally impossible, and backups two-part (`pg_dump` + data dir).
- **One process** serves API + SPA + SSE and runs the background scheduler in-process.
  No worker fleet, no broker *(ADR-003)*.
- **Two containers** in the compose stack: app + Postgres *(ADR-009)*.

---

## 2. Technology evaluation summary

Each subsection: problem → realistic alternatives → decision → why. Full detail in the
linked ADR.

### 2.1 Backend language & framework *(ADR-001)*

- **Problem:** serve a JSON CRUD API *and* move gigabytes through streaming endpoints,
  with a codebase a small team can audit.
- **Alternatives considered:**
  - *FastAPI (Python)* — async streaming is native; typing via Pydantic; enormous
    contributor pool; risk: Python CPU-bound work (thumbnails) must be isolated, and
    single-process throughput relies on asyncio discipline.
  - *Go (net/http or Echo)* — best raw transfer performance; single-binary deployment
    is lovely; cost: slower feature iteration for this domain, smaller pool of
    contributors who'll touch it, ORM/migration ecosystem weaker for rapid schema work.
  - *Node.js (NestJS/Fastify)* — one language across the stack; streaming is
    excellent (Node streams); cost: two ecosystems anyway (DB tooling is
    TS-weaker), NestJS ceremony is high for a small team.
- **Decision:** **FastAPI on Python 3.12+, uvicorn, one worker process** (scale-out is
  a documented non-goal for v1; multi-worker mode documented with its in-process
  rate-limit caveat).
- **Why:** the transfer path is I/O-bound (disk + network), where asyncio is strong;
  CPU work (thumbnails, hashing) is pushed to a bounded process/thread pool; Pydantic
  models give the OpenAPI contract for free (principle P8, API-first); Python is the
  most contributor-accessible of the three for a self-hosted OSS project.

### 2.2 Database *(ADR-002)*

- **Problem:** relational metadata (users, tree, shares, audit) with real constraints,
  plus decent name search, plus trivial Docker ops.
- **Alternatives:** *PostgreSQL* (constraints, `pg_trgm` search, JSONB for metadata,
  mature migrations); *SQLite* (zero container, perfect single-user fit, weaker
  concurrent-write story for audit + sessions churn, poorer tooling for backup during
  write load); *MariaDB/MySQL* (fine, no advantage here); *MongoDB* (wrong model —
  the tree and shares are relational).
- **Decision:** **PostgreSQL 16** via SQLAlchemy 2.0 (typed) + Alembic migrations.
  SQLite support is a **[FUTURE]** single-binary distribution mode — the ORM keeps the
  door open, but v1 tests against Postgres only (testing two databases doubles the
  matrix for zero MVP users).

### 2.3 Cache / broker *(ADR-003)*

- **Problem:** rate limiting, background jobs, SSE fan-out — things that *usually*
  imply Redis.
- **Analysis:** v1 has one process → in-process rate limiter (per-process accuracy is
  fine, documented), in-process asyncio job scheduler, SSE with direct in-memory
  listeners. Redis would be a third container benefiting nobody in v1 and a
  real operational cost for Raspberry Pi users.
- **Decision:** **no Redis.** Revisit triggers are explicit: ≥ 2 app replicas,
  cross-process job queue, or fan-out lag on SSE.

### 2.4 Storage *(ADR-004)*

- **Problem:** store bytes durably with dedup potential, zero trust in filenames, and
  an eventual path to S3 — without building a cloud SDK abstraction nobody asked for
  in v1.
- **Alternatives:** *path-mirroring store* (disk mirrors folder tree; intuitive;
  path-traversal-prone, rename/move = disk churn, dedup impossible); *content-addressed
  store* (blob path = content hash; traversal-proof, dedup natural, atomic finalize;
  cost: disk contents are opaque to humans — mitigated by an export/backup command
  that re-materializes a browsable tree); *S3-only* (wrong for local-first).
- **Decision:** **content-addressed local filesystem store** under a single
  configurable root: `data/blobs/ab/cd/<sha256>`, plus `data/uploads/<uuid>.part`
  for in-flight chunks and `data/thumbs/<file_id>/<size>.webp`. A minimal internal
  `Storage` protocol (open/read/write/delete/stat) isolates the two call sites that
  touch bytes, so an S3 driver is a [FUTURE] drop-in — but no driver abstraction,
  plugin config, or multi-backend UI ships in v1.

### 2.5 Upload protocol *(ADR-005)*

- **Problem:** resumable, chunked, cancellable uploads — correctly — without
  inventing a bespoke wire format that every client must implement.
- **Alternatives:** *raw multipart POST* (trivial; no resume, memory risk, timeout
  hell for 20 GB); *custom chunk API* (full control; reinvents offset semantics,
  race handling, client retry logic — and every future client reimplements it);
  *tus 1.0.0 resumable-upload protocol* (open standard: `POST` create, `HEAD` offset,
  `PATCH` append, `DELETE` cancel; mature clients — tus-js-client/Uppy; server spec
  is small enough to implement natively in FastAPI).
- **Decision:** **implement the tus 1.0.0 core subset natively** (creation,
  offset, chunk PATCH with `Upload-Checksum: sha256`, expiration, cancellation;
  `concat` deferred to Phase 3). Extensions beyond core are documented as
  unsupported and rejected with proper tus error responses.

### 2.6 Realtime *(ADR-006)*

- **Problem:** the UI should reflect other sessions' changes (file list updates, job
  progress, share counters) without polling storms.
- **Alternatives:** *WebSocket* (bidirectional — but we have no client→server stream
  need; more proxy-config friction); *SSE* (one-way server→client, plain HTTP,
  auto-reconnect built into browsers, trivially proxied); *polling* (baseline
  fallback anyway).
- **Decision:** **SSE at `/api/v1/events`** (session-authenticated; PAT-auth
  rejected with 403 — tokens are not event streams). Event types: `file.created`,
  `file.deleted`, `folder.changed`, `share.updated`, `job.progress`, `heartbeat`.
  Clients treat SSE as an optimization: TanStack Query invalidation on events, with
  polling fallback when the connection can't be established.

### 2.7 Frontend *(ADR-008)*

- **Problem:** a fast, accessible, mobile-first SPA that deploys as static files with
  no Node server in production.
- **Alternatives:** *Vite SPA* (static build the backend serves; simplest possible
  deployment); *Next.js* (SSR/SEO — irrelevant for an authenticated LAN tool; forces
  a Node runtime in the deployment story); *HTMX/server-rendered* (attractive
  simplicity, but the upload/transfer UX needs rich client state — progress managers,
  offline retry, drag-drop).
- **Decision:** **React 18 + TypeScript + Vite SPA**, TanStack Router (typed routes),
  TanStack Query (server state), Tailwind CSS + Radix primitives (a11y-correct
  dialogs/menus — detailed in 07-frontend-design.md). Built assets are served by
  FastAPI from `/app/static` with immutable-cache fingerprints; API stays on `/api/*`
  so reverse-proxy splits are trivial.

---

## 3. Backend architecture

### 3.1 Module layout

```text
backend/src/localdrop/
├── main.py              # app factory, middleware wiring
├── config.py            # pydantic-settings, LOCALDROP_* env
├── db.py                # engine, session factory, txn helpers
├── models/              # SQLAlchemy tables (one file per aggregate)
├── schemas/             # Pydantic request/response DTOs (OpenAPI source)
├── api/                 # routers: auth, files, folders, uploads,
│                        #          shares, admin, events, health
├── services/            # domain logic: upload_engine, download, shares,
│                        # thumbnails, cleanup, audit, ratelimit, discovery
├── storage/             # Storage protocol + LocalFilesystemStorage
├── jobs/                # scheduler loop + job definitions
└── staticfiles.py       # SPA serving (hash-fingerprinted)
```

Rule: **routers are thin** (auth → validate → call service → serialize); **services
own invariants** (quota checks, permission checks, atomic finalize); **models own
constraints**. A service function that touches storage and DB in one transaction is
the seam where crash-safety lives (see §5.5).

### 3.2 Request lifecycle

1. ASGI middleware assigns/propagates `X-Request-ID` (NFR-13).
2. Rate limiter (per route-class: auth 10/min/IP, share-access 60/min/IP,
   API default 300/min/user).
3. Auth dependency resolves session cookie **or** `Authorization: Bearer` PAT →
   `Principal` (user id, role, scopes). No global state; explicit dependency only.
4. Router validates via Pydantic → service → SQLAlchemy session (one per request,
   commit on success) → response DTO.
5. Structured log line: request id, principal, route, status, duration, bytes.

### 3.3 Background jobs (in-process scheduler)

A single asyncio task runs a tick loop (10 s) with jobs registered in code:

| Job | Cadence | Purpose |
|---|---|---|
| `finalize_hash` | continuous queue | Full-content sha256 of newly finalized blobs (status `pending → verified`); rename blob into place; enable dedup |
| `thumbnail` | continuous queue | WebP thumbs 256/1024 px via Pillow in a process pool (off-event-loop) |
| `upload_gc` | hourly | Delete expired/abandoned upload sessions + `.part` files (default TTL 7 d) |
| `trash_gc` | daily (02:00 local) | Purge trash older than retention; drop blob rows with zero references |
| `share_gc` | 5 min | Mark expired shares; enforce count limits |
| `session_gc` | hourly | Delete expired sessions |
| `integrity_sample` `[Phase 4]` | nightly | Re-hash a sample of blobs |

Jobs are **idempotent and lease-free** (single process makes this safe); every job
logs start/end/error with the same request-id discipline. If Redis-era multi-process
arrives, the scheduler gains a DB-backed lease — the job table already exists.

---

## 4. Storage architecture

### 4.1 Layout

```text
LOCALDROP_DATA_DIR/
├── blobs/ab/cd/<sha256>        # finalized content-addressed blobs
├── staging/<uuid>.part         # in-flight upload chunks (append-only)
├── thumbs/<file_id>/<n>.webp   # generated thumbnails
└── tmp/                        # atomic-rename scratch (same filesystem)
```

### 4.2 Rules

1. **No user input ever reaches a filesystem path.** Paths are composed exclusively
   from server-generated UUIDs and hex hashes. Filenames live only in the DB
   (validated, NFC-normalized, ≤ 255 bytes — see 06 §Threats).
2. **Append-only then atomic rename.** Chunks append to `staging/<uuid>.part`; a
   completed upload is `os.replace`d into its final name (or into the dedup target);
   readers therefore only ever see complete blobs (NFR-9).
3. **Durability before acknowledgment.** `fsync(file)` + `fsync(parent dir)` before
   the finalize transaction commits (NFR-10).
4. **Blob reference counting via `files` rows.** A blob with zero live/trashed file
   rows is GC-able; dedup (FR-F6) is a uniqueness lookup on `blobs.sha256`.
5. **One storage root in v1.** The `Storage` protocol (open/read/append/stat/delete/
   rename) is the only code allowed to touch `LOCALDROP_DATA_DIR`; multi-volume and
   S3 drivers are [FUTURE] implementations of it.

### 4.3 Why not path-mirroring (restated for implementers)

A mirrored tree invites: traversal bugs, cross-filesystem rename failures, permission
translation between OSes, and per-move I/O proportional to subtree size. The DB-tree +
blob-store split makes every file-tree operation a cheap indexed update and makes the
on-disk format hostile to nothing (defense in depth: even a path bug has no
user-controlled string to work with).

---

## 5. Upload architecture (the critical path)

### 5.1 Protocol mapping (tus subset on `/api/v1/uploads`)

| tus operation | Endpoint | Semantics |
|---|---|---|
| Creation | `POST /api/v1/uploads` | Body: JSON `{fileName, folderId, totalSize, mimeType?}` (deviation from tus metadata-header style: JSON is friendlier to hand-rolled clients; documented). → `201` + `Location: /api/v1/uploads/{id}` |
| Offset query | `HEAD /api/v1/uploads/{id}` | → `Upload-Offset`, `Upload-Metadata` echo. Enables resume after anything. |
| Chunk append | `PATCH /api/v1/uploads/{id}` | Headers `Upload-Offset: N`, `Content-Type: application/offset+json-less/octet-stream`, optional `Upload-Checksum: sha256 <base64>`. Server enforces contiguity; appends ≤ `LOCALDROP_UPLOAD_CHUNK_MAX` (default 8 MiB, hard cap 64 MiB) per request. |
| Cancel | `DELETE /api/v1/uploads/{id}` | → session row deleted, `.part` unlinked. |
| Expiration | server-side | `Upload-Expires` returned; GC per §3.3. |

### 5.2 Happy path (see 09-diagrams §3 for the sequence diagram)

1. **Create** — service validates: authenticated principal; folder exists & writable;
   `totalSize` ≤ max (FR-T5) + free-space check (≥ totalSize × 1.02); quota *(Ph 2)*.
   Row in `upload_sessions` (status `active`, offset 0, expires now+7 d); empty
   `staging/<uuid>.part` created.
2. **Chunk append** — read request body in bounded chunks (64 KiB read loop) →
   append to `.part` → verify per-chunk checksum if provided → update offset row.
   Offset updates are committed every chunk (default; batched at NFR-affecting rates
   is [FUTURE] tuning).
3. **Finalize** (offset == totalSize) — `fsync` → transaction: create `blobs`/`files`
   rows (status: `pending`), mark session `finalized`. Respond `201` with the
   file resource. **Hash is not yet computed.**
4. **Background hash** — `finalize_hash` job streams the blob (1 MiB reads),
   computes sha256, `os.replace`s `staging → blobs/ab/cd/<hash>` (or links to an
   existing identical blob and deletes the staging file — dedup), sets
   `blobs.status = verified`, publishes `file.created` SSE.
5. **File appears in UI** when the client receives the finalize response (list
   refresh), with a subtle "verifying integrity" badge until `verified` — honesty in
   the UI about what the server has guaranteed.

### 5.3 Failure & recovery matrix

| Failure | Consequence | Recovery |
|---|---|---|
| Client crash mid-upload | `.part` sits, session `active` | Client `HEAD`s by upload URL (persisted client-side in IndexedDB), resumes at offset |
| Server restart mid-upload | Same; offset persisted per-chunk in DB | Resume works identically after reboot |
| Chunk corruption in transit | Optional checksum mismatch → `460` *(tus-style conflict)*; offset not advanced | Client retries chunk |
| Disk full mid-append | Append fails; offset row not advanced (append-then-commit order) | Client retries after admin frees space; partial `.part` retained |
| Server crash between fsync and DB commit | Orphan `.part` with no row | `upload_gc` removes unreferenced `.part` files |
| Crash after DB commit but before rename | Blob row `hash_pending`, file stuck | `finalize_hash` retries from staging (job is idempotent: staging file remains source of truth until rename ack) |
| Duplicate upload of existing content | Staging hashed → matches existing blob → staging deleted, `files` row references existing blob | No extra disk (FR-F6) |

### 5.4 Memory & concurrency discipline (the NFR-3 rules)

- Request bodies are **never** fully buffered: upload PATCH streams to disk in 64 KiB
  reads; downloads stream from disk in 256 KiB–1 MiB reads.
- Hashing/thumbnails run in a **bounded process pool** (`max_workers = 2` default) —
  never on the event loop.
- Concurrent upload sessions per user capped (`LOCALDROP_UPLOAD_SESSIONS_MAX`, default
  20); the UI schedules ≤ 3 parallel files.
- uvicorn is configured with hard limits: `--limit-concurrency 100`,
  `--timeout-keep-alive 65` (proxy-friendly), body-size guard at the router level
  per endpoint (tus PATCH has no whole-body cap by design — chunks are capped).

### 5.5 The one transaction rule

Every mutation that spans DB + storage does storage first, DB second, and every
storage operation is either idempotent or compensatable by GC:
`storage write → commit row` (crash ⇒ orphan file, GC cleans) — never
`commit row → storage write` (crash ⇒ dangling reference, user-visible corruption).
This ordering rule is restated in the Build Contract and enforced in code review.

---

## 6. Download architecture

- **Endpoint:** `GET /api/v1/files/{id}/content` (session/PAT) and
  `GET /api/v1/shares/{token}/files/{id}/content` (public share path — token grants
  access to a file subtree; every access re-checks share validity, expiry, count
  limit, and password via the share session cookie).
- **Streaming:** Starlette `FileResponse` (Range/If-Range support; single-read
  validation in tests), fallback to manual async-iterator streaming if probing shows
  platform sendfile issues `[NEEDS VALIDATION — benchmark in Phase 1]`.
- **Headers:** `ETag: "<sha256>"` (strong, once verified), `Last-Modified`,
  `Accept-Ranges: bytes`, `Content-Length`, `Content-Type` from DB mime,
  `Content-Disposition: inline` for preview-safe types / `attachment;
  filename*=UTF-8''<encoded>` otherwise (policy table in 06 §4).
- **Range:** single-range supported (multi-range is `[FUTURE]`; download managers
  survive), `206` with correct `Content-Range`, `416` handling, open-ended ranges
  (`bytes=N-`) supported for resume.
- **Download tracking:** `share_downloads` row per public-share content request
  (deduplicated per share-session to count humans, not segments); counts feed
  limit enforcement (FR-S2) and share stats. Authenticated (non-share) downloads
  record an audit event, not per-segment rows.
- **Hot path rule:** no DB writes in the streaming loop; tracking is buffered and
  flushed post-response.

---

## 7. Local-network discovery — the honest matrix

What we *ship* in MVP: **QR + URLs at startup** (always works), **mDNS
best-effort**, and this documented reality matrix (FR-L3). What we do not pretend:
that a browser can be made to discover arbitrary services — it cannot.

| Platform | `http://localdrop.local` in default browser | Notes |
|---|---|---|
| macOS (Safari/Chrome) | ✅ Yes | Native mDNS resolver (Bonjour). |
| iOS (Safari/Chrome) | ✅ Yes | mDNS resolved by the OS. |
| Windows 10/11 (Edge/Chrome/Firefox) | ✅ Generally yes | Native mDNS since Win10 1703; **caveat:** if a *printer* named `localdrop` exists, or mDNS is disabled by policy/GPO, fails — hence QR/URL fallback. `[NEEDS VALIDATION on target builds]` |
| Android 12+ (Chrome) | ⚠️ Partial | Historically Android ignored `.local` in browsers; modern releases resolve via OS mDNS in many ROMs but behavior is OEM-dependent. **Treat as unreliable; QR is the primary Android path.** `[NEEDS VALIDATION across OEMs]` |
| Android ≤ 11 | ❌ Mostly no | Use QR / typed IP. |
| Linux desktop | ⚠️ Depends | Works when `nss-mdns` + Avahi installed (most GNOME/KDE spins ship it); minimal/server installs don't. |

mDNS advertisement mechanics *(ADR-009)*: the app itself sends announcements only when
it can — inside default bridge networking it **cannot** (multicast doesn't cross the
Docker bridge). MVP posture: `docker-compose.yml` ships a documented, **opt-in**
`network_mode: host` profile (Linux) under which the app announces
`_localdrop._http._tcp.local` via `python-zeroconf`; otherwise it prints
`http://<detected-lan-ip>:<port>` + QR and stays honest. `[NEEDS VALIDATION: zeroconf
stability under host networking, and behavior on macOS/Windows Docker Desktop — both
likely "no mDNS", matrix above stands.]`

LAN IP detection: enumerate non-loopback IPv4s via stdlib (`socket.getaddrinfo` +
connect-UDP trick to default gateway), de-prefer virtualization bridges
(docker/virtualbox/WSL prefixes filtered by interface-name heuristics), print all
candidates, QR-encode the first.

---

## 8. Realtime communication (SSE) detail

- Endpoint `GET /api/v1/events` (`text/event-stream`), one long-lived connection per
  browser tab; session-auth only; heartbeat comment every 20 s keeps proxies from
  idling out.
- Event envelope: `id` (monotonic per connection), `event` (type), `data` (JSON
  matching an API DTO — e.g. a `file.created` event carries the same file object as
  `GET /api/v1/files/{id}`).
- Server side: an in-process `EventBus` (asyncio queues per subscriber, bounded,
  drop-oldest on overflow — a dropped event just means the client falls back to a
  query invalidation). Services publish; routers do not.
- Client side: EventSource → TanStack Query cache invalidation. **No correctness
  depends on SSE** — every SSE-driven refresh has a polling fallback
  (30 s) so first-load and proxied environments work regardless.

---

## 9. Configuration (environment contract)

`LOCALDROP_*` environment variables via pydantic-settings (12-factor, Docker-idiomatic;
a config-file layer is `[FUTURE]` — env + compose `env_file` covers the persona set).

| Variable | Default | Notes |
|---|---|---|
| `LOCALDROP_DATA_DIR` | `/var/lib/localdrop` | Storage root (volume mount point). |
| `LOCALDROP_DATABASE_URL` | *(required)* | `postgresql+asyncpg://…` |
| `LOCALDROP_SECRET_KEY` | *(required, ≥ 32 chars)* | Session/token HMAC pepper. Generated by entrypoint if unset **only in dev mode**; production refuses to boot without it. |
| `LOCALDROP_PUBLIC_URL` | *(auto-detected)* | Used in share-link construction; set when behind a proxy with a hostname. |
| `LOCALDROP_PORT` | `8080` | HTTP listen port. |
| `LOCALDROP_MAX_UPLOAD_BYTES` | `107374182400` (100 GiB) | `0` = unlimited. |
| `LOCALDROP_UPLOAD_CHUNK_MAX_BYTES` | `8388608` (8 MiB) | Hard cap 64 MiB. |
| `LOCALDROP_UPLOAD_SESSIONS_MAX` | `20` | Per user. |
| `LOCALDROP_UPLOAD_TTL_DAYS` | `7` | Staging GC. |
| `LOCALDROP_TRASH_RETENTION_DAYS` | `30` | |
| `LOCALDROP_SESSION_IDLE_MINUTES` | `10080` (7 d) | |
| `LOCALDROP_SESSION_ABSOLUTE_MINUTES` | `43200` (30 d) | |
| `LOCALDROP_RATE_LIMIT_*` | *(per-class defaults)* | See 05-api §rate limits. |
| `LOCALDROP_LOG_LEVEL` / `LOCALDROP_LOG_FORMAT` | `info` / `json` | `dev` format for humans. |
| `LOCALDROP_MDNS_ENABLED` | `false` | Only meaningful with host networking. |
| `LOCALDROP_DEV_MODE` | `false` | Never set in production; gates dev conveniences. |

Full table with validation rules lives in 08-engineering §4; the authoritative list is
`backend/src/localdrop/config.py` (single source, exported to docs by a CI check that
fails on drift `[Phase 1 tooling]`).

---

*Next: [04 — Database schema](04-database.md). Diagrams: [09](09-diagrams.md).*
