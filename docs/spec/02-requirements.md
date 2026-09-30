# 02 — Requirements, Roadmap & MVP

*Status: Proposed. Requirement IDs (FR-/NFR-) are referenced by the roadmap, API, and
testing documents.*

---

## 1. Functional requirements

Priorities: **M** = MVP (Phase 1), **2** = Phase 2, **3** = Phase 3, **4** = Phase 4,
**5** = Phase 5. Anything not marked M must not block the MVP release.

### 1.1 Accounts & authentication

| ID | Requirement | Phase |
|---|---|---|
| FR-A1 | First-run onboarding creates the owner account (setup token printed to server console, valid 15 min, single use) | M |
| FR-A2 | Login with username + password; logout | M |
| FR-A3 | Sessions: server-side, expire after configurable idle/absolute limits; user can list and revoke own sessions | M |
| FR-A4 | Change own password (requires current password) | M |
| FR-A5 | Personal access tokens (PATs) for API use; create/list/revoke; scopes `read`/`write` | M |
| FR-A6 | Password reset via configured SMTP; if SMTP not configured, owner reset via console command | 2 |
| FR-A7 | Multiple user accounts (admin-created), self-registration opt-in flag (default **off**) | 2 |
| FR-A8 | Email verification | 2 |
| FR-A9 | OAuth (generic OIDC provider) | 5 `[FUTURE]` |

### 1.2 Files & folders

| ID | Requirement | Phase |
|---|---|---|
| FR-F1 | Upload files via browser (drag & drop, file picker, *folder* drag & drop where the browser supports it) | M |
| FR-F2 | Virtual folder tree: create, rename, move, delete folders | M |
| FR-F3 | File operations: rename, move, copy, delete (soft-delete + trash with restore, purge after 30 d) | M |
| FR-F4 | Multi-select + bulk actions (move, delete, download-as-zip `[3]`) | M (zip: 3) |
| FR-F5 | List/search: sort by name/size/date, filter by type, name search (pg_trgm) | M |
| FR-F6 | Duplicate handling: same content re-uploaded → references existing blob, second DB row (no wasted disk) | M |
| FR-F7 | Storage quota per user and per instance | 2 |
| FR-F8 | Multi-volume storage (attach a second disk, choose per-folder) | 4 `[FUTURE]` |

### 1.3 Transfer

| ID | Requirement | Phase |
|---|---|---|
| FR-T1 | Chunked, resumable uploads (tus subset): create session, query offset, append chunks, cancel; survive client reload and server restart | M |
| FR-T2 | Per-chunk integrity (sha256 checksum header) and end-of-upload full-content hash | M |
| FR-T3 | Upload progress, cancellation, retry, and bounded concurrency (default 3 parallel files) in UI | M |
| FR-T4 | Streaming downloads with `Range`/`If-Range`/`ETag` (resume-capable) | M |
| FR-T5 | Configurable max upload size (default 100 GiB; 0 = unlimited) and rejected-with-clear-error behavior | M |
| FR-T6 | Download-as-zip for folders/multi-select (server-generated, streamed, never buffered) | 3 |
| FR-T7 | Integrity re-verification job (nightly sample; on-demand per file) | 4 |

### 1.4 Sharing

| ID | Requirement | Phase |
|---|---|---|
| FR-S1 | Public share links for files (auth-free access) | M |
| FR-S2 | Share options: expiry timestamp, download-count limit, password, allow/disallow listing for folders | M |
| FR-S3 | Revoke share; list own shares with usage counters | M |
| FR-S4 | QR code for share URL (generated client-side; no external service) | M |
| FR-S5 | Public folder shares (browse a shared subtree without an account) | 2 |
| FR-S6 | Authenticated internal shares (share-to-user with role: viewer/editor) | 2 |

### 1.5 Previews

| ID | Requirement | Phase |
|---|---|---|
| FR-P1 | Image thumbnails (JPEG/PNG/WebP/GIF/AVIF) + inline lightbox | M |
| FR-P2 | PDF inline preview (browser-native `<embed>` + `Content-Disposition` policy) | M |
| FR-P3 | Text/code preview with size cap (256 KiB) and charset detection | M |
| FR-P4 | Audio/video: metadata + native player (`<video>`/`<audio>` relies on browser codecs) | M |
| FR-P5 | Unsupported formats: icon + download only — **never** sniff-and-render untrusted types | M |
| FR-P6 | Video filmstrip thumbnails (ffmpeg sidecar, optional container) | 4 `[FUTURE]` |
| FR-P7 | Office document preview | 5 `[FUTURE]` |

### 1.6 Admin & operations

| ID | Requirement | Phase |
|---|---|---|
| FR-O1 | Health endpoints: liveness + readiness (DB + storage reachable) | M |
| FR-O2 | Structured JSON logs with request IDs; human-readable dev mode | M |
| FR-O3 | Basic Prometheus `/metrics` (request counts/latencies, storage usage, upload sessions) | M |
| FR-O4 | Admin dashboard: storage usage, active sessions, share stats, recent audit events | 2 |
| FR-O5 | User management UI (create/disable users, reset passwords) | 2 |
| FR-O6 | Instance settings UI (registration flag, quotas, limits) | 4 |
| FR-O7 | Audit log browsing/export (CSV/JSON) in UI | 4 |

### 1.7 Local network experience

| ID | Requirement | Phase |
|---|---|---|
| FR-L1 | On startup: detect LAN IPv4s, print clickable URLs + QR (console and onboarding page) | M |
| FR-L2 | mDNS advertisement of `_localdrop._http._tcp.local` → `localdrop.local` where host networking permits `[NEEDS VALIDATION]` | M (best-effort) |
| FR-L3 | Documented per-platform reality matrix (see 03-architecture §7) | M |
| FR-L4 | SSDP/UPnP-based discovery companion page | 4 `[FUTURE]` |

---

## 2. Non-functional requirements

| ID | Category | Requirement | Target |
|---|---|---|---|
| NFR-1 | Performance | Upload/download throughput on LAN ≥ 90 % of raw disk/network for single stream (1 GbE: ≥ 100 MB/s) | MVP |
| NFR-2 | Memory | RSS of the app container under any transfer workload | < 250 MB (excluding Python baseline) |
| NFR-3 | Memory | Any single request body handling | **Bounded** — chunk-size constant, never file-size |
| NFR-4 | Concurrency | Simultaneous active upload sessions (default config) | ≥ 20 without degradation |
| NFR-5 | Startup | Cold start to ready (compose up, warm images) | < 15 s |
| NFR-6 | Usability | First-run to first successful transfer by a non-technical user | < 5 min |
| NFR-7 | Security | OWASP ASVS L2 for the authenticated surface; L1+ for public share surface | MVP |
| NFR-8 | Accessibility | WCAG 2.2 AA on all MVP pages | MVP |
| NFR-9 | Availability | Crash of one upload must never corrupt existing files (atomic finalize only) | MVP |
| NFR-10 | Data durability | Completed upload durable across ungraceful shutdown (fsync before finalize-ack) | MVP |
| NFR-11 | Portability | Images for linux/amd64 + linux/arm64 (Raspberry Pi 4+) | MVP |
| NFR-12 | Offline | Zero outbound network calls at runtime | MVP |
| NFR-13 | Observability | Every request carries a request ID propagated to logs and error responses | MVP |
| NFR-14 | Recoverability | Documented backup/restore tested in CI monthly | Phase 2 (docs: MVP) |
| NFR-15 | API stability | `/api/v1` contract stable across minors; deprecation notice one minor before removal | From MVP |

---

## 3. Feature prioritization summary

**Build (MVP):** single owner account; upload/download/delete/rename/move/copy;
folders; search/sort; multi-select; resumable uploads; streaming downloads; share
links (expiry/password/limit/revoke/QR); previews (image/PDF/text/AV metadata);
trash; PATs; health/metrics/logs; LAN QR onboarding; Docker Compose deployment.

**Explicitly deferred (do not build early):** multi-user & registration, per-folder
ACLs, quotas, email, zip download, video thumbnails, S3/MinIO storage, multi-volume,
CLI, plugins, OAuth, AV scanning, E2EE. Rationale in
[10-risks-open-questions.md](10-risks-open-questions.md); the MVP discipline is that
*these features are designed for* (schema has the columns; interfaces have seams) but
*not built*.

---

## 4. Roadmap

### Phase 0 — Architecture *(current)*
- **Goal:** specification, repo foundation, CI skeleton.
- **Tasks:** this document set; ADRs ratified; repo scaffold; empty pipelines green.
- **Acceptance:** maintainer signs off on the Build Contract; `docs/` merges to main.

### Phase 1 — MVP
- **Goal:** the smallest honest public release (§5 below).
- **Features:** everything marked M above.
- **Engineering tasks:** backend service skeleton; DB migrations v1; tus upload
  engine; streaming download path; share engine; auth; thumbnails; SPA file browser;
  compose stack; test suites L1–L3; install docs.
- **Acceptance:** every M FR has an automated test; a non-technical tester completes
  UC-1, UC-2, UC-4 unaided; security checklist (06 §5) fully checked; images published
  to ghcr for both architectures.

### Phase 2 — Real users
- **Goal:** teams and households.
- **Features:** user accounts + admin management, per-folder sharing (viewer/editor),
  quotas, email (reset/verification), public folder shares, admin dashboard,
  audit-log UI polish, i18n extraction (≥ 2 locales).
- **Acceptance:** UC-10 end-to-end; permission-matrix test suite green; ASVS L2 re-check.

### Phase 3 — Performance & large transfers
- **Goal:** multi-hundred-GB comfort.
- **Features:** zip download streaming, sendfile/zero-copy where available, upload
  parallelism per file (tus `concat`), background hash scheduling, perf test suite in CI
  (nightly), integrity sampling.
- **Acceptance:** NFR-1/3/4 verified by CI numbers, not claims.

### Phase 4 — Self-hosting maturity
- **Goal:** operator confidence.
- **Features:** instance settings UI, audit export, backup/restore helper command,
  multi-volume storage `[DECISION REQUIRED]`, optional ClamAV sidecar, mDNS/SSDP
  polish, restore tests in CI.
- **Acceptance:** full upgrade + rollback-documentation dry-run against a v1 dataset.

### Phase 5 — Ecosystem
- **Goal:** developers build on LocalDrop.
- **Features:** generated API client libraries, CLI (`localdrop upload|share|status`),
  OAuth/OIDC login, plugin hooks (post-upload, post-share), S3/MinIO storage backend
  `[FUTURE]`.
- **Acceptance:** CLI performs UC-9 without a browser; plugin example in-tree.

---

## 5. MVP definition

**LocalDrop v1.0.0 is:** a single-owner, self-hosted drop box.

In scope (all must ship): owner onboarding via console token → web login →
upload files of any practical size with resume → browse/manage in a responsive,
accessible SPA → stream downloads with resume → create public links
(expiry/password/limit/revoke/QR) → preview images/PDF/text/AV metadata → trash with
restore → PATs for API use → health/metrics/logs → deploy via one compose file →
backup/restore documented and testable → installed behind any reverse proxy with TLS.

Explicitly out of scope for v1.0.0: any second user account, registration, shared
folders, quotas, email, zip downloads, cloud storage, CLI, plugins.

**Why this is honest:** it fully serves Personas A (home user), B (developer via API),
and D (self-hoster). Persona C (teams) waits for Phase 2 so permissions arrive as a
designed whole instead of an accretion. A single-owner deployment is the modal
self-hosted install and is complete — not a demo — on day one.

**Release gates (all blocking):** test matrix of §08 green; security checklist §06
green; WCAG AA audit on core pages; docs (install, config, reverse proxy, backup)
complete; fresh-VM install script rehearsal passed; no `[NEEDS VALIDATION]` items
remaining on MVP features.

---

*Next: [03 — Architecture & technology evaluation](03-architecture.md).*
