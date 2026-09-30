# ADR-005 — Upload protocol: tus 1.0.0 subset, implemented natively

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

Uploads must be resumable after client reload, network drop, or **server reboot**;
chunked with integrity checks; cancellable; and implementable by third-party clients
(API-first, P8) without reading our source.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **Raw multipart POST** | One line of framework code | No resume; proxies/browsers time out on multi-GB; whole-body handling pressure; 20 GB in one request is abuse of HTTP |
| B | **Custom chunk API** | Full control; no external spec to satisfy | We reinvent offset semantics, conflict codes, retry rules — and every future client reimplements the client half; interop story = "read our docs" |
| C | **tus 1.0.0 open standard** (create/HEAD/PATCH offset/DELETE, expiration, checksum extension) | Battle-tested protocol; mature clients (tus-js-client, Uppy) for free; CLI/tools ecosystem; a documented deviation budget we control | Server must be implemented (no canonical FastAPI tus lib we'd trust — [NEEDS VALIDATION: re-survey `tus-fastapi`-class libs at Phase 1 start; decision stands on "natively implementable in ~300 LOC" either way) |
| D | **S3 multipart semantics** | Familiar to devs | Presumes S3-shaped storage; wrong for v1 (ADR-004) |

## Decision

**Option C, implemented natively** in FastAPI at `/api/v1/uploads` per 03 §5.1:
creation (JSON body — a documented, deliberate deviation for hand-rolled clients),
HEAD offset, PATCH append with `Upload-Offset` + optional
`Upload-Checksum: sha256 <b64>`, DELETE, server-side expiration + GC. Unsupported
tus extensions (concat, termination-of-others) get proper tus error responses.
Chunk default 8 MiB, hard cap 64 MiB; minimum 64 KiB (anti-write-storm, 06 §2.10).
`tus concat` (parallel assembly) is Phase 3 [FUTURE].

## Consequences

- **+** Uppy/tus-js give the SPA a proven upload engine; resume-after-reload via
  IndexedDB-persisted URLs is client-tier, not protocol-tier, work.
- **+** Future CLI (08 §11) gets resumable upload from an existing client library.
- **−** We own protocol correctness — mitigated by the exhaustive L2 lifecycle suite
  (kill -9 at every step) and checksum verification per chunk.
- **−** tus's `Upload-Metadata` header convention is bypassed at creation (JSON body)
  — documented deviation, kept small.
