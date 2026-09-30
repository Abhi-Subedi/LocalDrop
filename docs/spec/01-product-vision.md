# 01 — Product Vision

*Status: Proposed. Sections: executive summary, vision, problem, users, use cases,
principles, privacy philosophy.*

---

## 1. Executive summary

LocalDrop is a self-hosted, open-source file-sharing platform built for **local
networks first**, with optional remote access. You run one small Docker stack on a
machine you own — a home server, NAS, Raspberry Pi, desktop, or VPS — and every device
on your network gets a fast, private, browser-based drop box with no accounts on
anyone else's cloud.

The differentiators, in priority order:

1. **Local-network experience.** Startup prints a QR code and LAN URL; the server
   advertises itself via mDNS (`localdrop.local`) where the platform allows it. Getting
   from "installed" to "file on my phone" takes under five minutes, with an IP fallback
   that always works.
2. **Real file engineering.** Resumable chunked uploads (tus-compatible), streaming
   downloads with HTTP range support, content-addressed storage with dedup-ready
   hashing — all with bounded RAM, so a 20 GB upload is as ordinary as a 20 KB one.
3. **Privacy as architecture, not policy.** Zero telemetry by default, fully offline
   capable, no external calls, delete-means-delete. The instance administrator sees
   only what the server must record to function.
4. **Honest scope.** The MVP is single-owner with public share links — genuinely
   releasable — and multi-user teams, shared folders, S3 storage, CLI, and plugins are
   explicitly phased rather than half-built.

The recommended architecture is deliberately boring and small: **FastAPI + PostgreSQL
+ a content-addressed local filesystem store + a React/Vite SPA**, deployed as two
containers (app + database). No Redis, no message queue, no microservices, no
Kubernetes. Full rationale in [ADR-001 … ADR-009](../adr/ADR-001-backend-framework.md);
the binding summary is the [Build Contract](11-build-contract.md).

---

## 2. Product vision

> **"Your files, your network, your server."**

LocalDrop wants to be the self-hosted answer to "can you just send me that file?" —
the piece of infrastructure that makes moving files between your own devices (and to
people you choose) instant, private, and independent of any company's business model.

In five years, a healthy LocalDrop is: thousands of small deployments (homes, labs,
teams), a small but steady contributor base, a stable REST API with a CLI and client
libraries, and a reputation for being the tool that *never* phones home.

**What LocalDrop is not:** a cloud product, a sync engine (no bidirectional device
sync in the foreseeable roadmap), a collaborative document platform, or a Google Drive
clone. LocalDrop is a *drop box*: files go in, files come out, links share them.

---

## 3. Problem statement

Moving files between devices and people on a network you control is still absurdly
frictional in 2026:

- **Consumer clouds** (Drive, Dropbox, WeTransfer) are slow on LAN (uploads round-trip
  through the internet), impose size quotas, require accounts, and are inappropriate
  for private files.
- **OS-native sharing** (AirDrop, Nearby Share, SMB, `scp`) is platform-locked,
  terminal-hostile for non-technical users, and nonexistent as a cross-platform
  browser experience.
- **Existing self-hosted tools** either target power users only (require reverse-proxy
  + TLS + DNS knowledge to be usable), are general-purpose clouds too heavy for the
  job (Nextcloud), or are abandonware with weak security stories.

The gap: a tool that is *simultaneously* trivial for a non-technical user to run and
trustworthy enough for a security engineer to expose to their LAN. That dual bar —
**simple for non-technical users, powerful for developers, secure by default** — is
the design tension LocalDrop commits to resolving.

---

## 4. Target users

| Persona | Environment | Primary needs | Success looks like |
|---|---|---|---|
| **A — Home user** | Laptop + phone + home Wi-Fi; zero server knowledge | Move photos/videos/PDFs between own devices and to family members | Scans QR code, drops a file, opens it on phone. Never sees a terminal. |
| **B — Developer** | Linux server / Pi / NAS / VPS; terminal fluent | API, Docker, config, logs, eventually CLI + integrations | `docker compose up -d`, hits REST API with a personal access token, reads structured logs. |
| **C — Small team** | Shared office server or small VPS | Accounts, shared folders, permissions, private links | Team members log in, share a folder structure, revoke a contractor's link. *(Phase 2)* |
| **D — Self-hosting enthusiast** | Homelab with reverse proxy, TLS, backups | Control, no lock-in, custom storage location, HTTPS, backup/restore | Puts LocalDrop behind Caddy/Traefik, sets storage volume, schedules backups, updates via compose pull. |

**Design consequence:** every feature must be usable by A *through the UI alone*, and
every feature must be operable by D *without fighting defaults*. B is served by the
API-first rule (§6, P8). C is explicitly not served by the MVP — teams get a real
permission model in Phase 2 rather than a broken one in Phase 1.

---

## 5. Core use cases

These drive the architecture; each maps to flows in [09-diagrams.md](09-diagrams.md).

| # | Use case | Actor | Architecture it forces |
|---|---|---|---|
| UC-1 | First run: install on server, open on phone via QR | A, D | LAN IP detection, QR output, onboarding wizard |
| UC-2 | Upload 18 GB video from laptop, network drops at 60 %, resume | A, B | tus resumable uploads, chunked disk appends, upload-session GC |
| UC-3 | Download a 30 GB archive on an unreliable connection with pause/resume | B | HTTP range requests, ETag/If-Range, streaming with bounded RAM |
| UC-4 | Send a read-only link to a 2 GB folder, expiring in 48 h, password protected | A, C | Public share tokens, per-share policy, no-auth download path |
| UC-5 | Browse, rename, move, delete, search files from a phone | A | Responsive file browser, virtual tree in DB, pg search |
| UC-6 | Preview photos inline; check a PDF/text without downloading | A, C | Thumbnail service, sandboxed previews, content-type policy |
| UC-7 | Admin rotates storage to a bigger disk, restarts, nothing breaks | D | Configurable storage root, paths in DB not on disk |
| UC-8 | Restore after disk failure from backup | D | Documented backup = `pg_dump` + data dir; restore procedure |
| UC-9 | Script uploads from CI/server via API | B | PAT auth, full REST coverage of UI actions |
| UC-10 | Two flatmates both have accounts; one shares a folder read-only | C *(Phase 2)* | User accounts, per-folder ACLs |

Non-goals for v1 (restated as use cases we refuse): device-to-device sync, real-time
collaborative editing, public sign-up communities, end-to-end encrypted vaults
*(the server is trusted; E2EE is a research item, see
[10-risks-open-questions.md](10-risks-open-questions.md))*.

---

## 6. Product principles

These ten principles are the tie-breakers for future contributors. When two designs
are otherwise equal, the one that honors more principles wins.

1. **Local first, remote optional.** Every feature must work on an isolated LAN with
   no internet. Remote access is an add-on (reverse proxy + TLS), never a requirement.
2. **The server belongs to the user.** Zero telemetry, zero outbound calls, zero
   accounts on our side (there is no "our side"). No feature may require an external
   service. *[Confirmed — product-level]*
3. **Secure by default, not by configuration.** Safe defaults ship on: sessions are
   HttpOnly + SameSite, uploads are size-checked, share links are unguessable, rate
   limits are on. Insecurity should require deliberately switching it off.
4. **Five minutes to first file.** One container pull, one volume, QR code, done.
   Any setup step that can be eliminated must be.
5. **Streams, never buffers.** RAM usage is bounded and independent of file size.
   No code path may load a file (or a request body) wholesale into memory.
6. **Progressive complexity.** Defaults are simple; power (API, config, storage
   layout) is discoverable. Features arrive layered — never dump the full matrix on
   a first-time user.
7. **Boring technology, excellent implementation.** Prefer proven components with
   small surface area; spend the innovation budget on the transfer path and UX, not
   on exotic infrastructure.
8. **API-first internals.** The web UI consumes the same versioned REST API we
   document publicly. No UI-only backdoors.
9. **Every screen is a phone screen first.** Mobile is a first-class target (most
   transfers involve a phone), with desktop as the power layout — not the reverse.
10. **Data honesty.** Delete means delete (and GC actually reclaims space). Docs tell
    the truth about what the server records. Changes that would record *more* about
    users require justification in an ADR.

---

## 7. Privacy philosophy (summary)

Full model in [06-security-privacy.md § Privacy](06-security-privacy.md). The stance:

- **Collected by default: nothing** beyond what the server needs to function —
  account row, file metadata, audit events (security-relevant actions only).
- **Telemetry: none, ever.** No crash reporting, no version pings, no analytics.
  The codebase carries a test asserting no outbound HTTP at runtime
  *(see testing strategy, 08-engineering.md)*.
- **Fully offline capable.** All fonts, icons, and assets are self-hosted; the SPA
  bundle makes zero third-party requests.
- **Admin visibility is bounded:** an admin can see file metadata and audit events,
  not file *contents* unless they open them like any user (single-owner MVP: the
  owner owns everything by definition; this matters from Phase 2 on).
- **Users can see what's recorded about them** *(Phase 2: account page shows sessions
  and audit history)*.

---

*Next: [02 — Requirements, roadmap, and the MVP definition](02-requirements.md).*
