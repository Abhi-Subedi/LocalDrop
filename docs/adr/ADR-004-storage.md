# ADR-004 — Storage: content-addressed local filesystem blob store

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

We must store bytes durably on a user-chosen local path; treat filenames as hostile
forever; dedup identical content cheaply; keep renames/moves O(1); and leave a
credible door open to S3/MinIO later — without building a cloud abstraction layer
nobody needs in v1.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **Path-mirroring** (disk tree mirrors folder structure) | Disk is human-browsable | Path traversal surface; renames/moves = disk churn; no dedup; permission semantics per-OS; worst option on every axis that matters |
| B | **Content-addressed blob store** (DB owns the tree; blobs named by sha256) | Traversal-proof by construction; dedup trivial (unique index); atomic finalize; rename/move = DB row; backup-friendly stable filenames | Disk not human-navigable (mitigated: export command + docs); hash computed post-finalize |
| C | **S3/MinIO-only** | Infinite scale, offloaded durability | Wrong for local-first; adds SDK + network hop; most installs have a perfectly good disk |
| D | **B: abstraction now, S3 driver later** | Max future flexibility | YAGNI in v1: no users asking; every byte-path bifurcation doubles testing |

## Decision

**Option B now, D-shaped seam only:** layout `blobs/ab/cd/<sha256>`, `staging/`,
`thumbs/` under `LOCALDROP_DATA_DIR`. A minimal internal `Storage` protocol
(open/append/read/stat/delete/rename) is the only code touching the data dir — that
is the entire S3-ready surface. **No driver interface, backend config, or multi-
volume UI ships in v1** (BC-20). S3 remains [FUTURE] with an open sub-question
(direct-to-S3 tus vs. proxy) tracked in 10 §3.

## Consequences

- **+** Security (BC-3/BC-11) becomes structural rather than vigilant.
- **+** Identical re-uploads cost zero extra disk (FR-F6) via one index lookup.
- **−** "Where are my files on disk?" gets the honest answer: in LocalDrop — with an
  export command planned; docs must set this expectation early.
- **−** Full-content sha256 is computed in the background post-finalize; the UI shows
  a "verifying" state until done (truthful, and rarely noticed).
