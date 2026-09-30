# ADR-001 — Backend framework: FastAPI

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

The backend must (a) expose a typed REST API, (b) stream gigabyte-scale request/
response bodies with bounded RAM, (c) run background jobs (hashing, thumbnails, GC),
(d) be auditable by a small team and hackable by open-source contributors, and
(e) deploy in one small container on ARM SBCs.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **FastAPI (Python 3.12 + uvicorn)** | Async streaming native; Pydantic → OpenAPI for free (P8); largest contributor pool for self-hosted OSS; SQLAlchemy maturity | GIL: CPU work must be pooled off-loop; interpreter perf is fine for I/O but not for CPU |
| B | **Go (net/http or Echo)** | Best transfer throughput; single static binary; great concurrency | Slower iteration on this domain (schema/migration/DTO ergonomics); smaller contributor pool for the project's audience; two languages in repo anyway (SPA) |
| C | **Node.js (Fastify/NestJS)** | One language across stack; Node streams excellent | NestJS ceremony vs. small team; weaker typed-DB story; no advantage on the hard part (transfer path is equal) |
| D | **Rust (Axum)** | Peak performance & correctness | Highest contribution friction; slowest feature velocity for a v1 team |

## Decision

**FastAPI, single process, uvicorn, one worker.** CPU-bound work (image decode,
hashing of finalized blobs) goes to a bounded process pool. Scale-out (multi-worker/
multi-host) is an explicit v1 non-goal; when revisited, it forces the Redis
conversation (ADR-003 triggers).

## Consequences

- **+** OpenAPI contract generated from the same models that validate requests —
  drift is structurally impossible (P8 satisfied cheaply).
- **+** Contributor-accessible: Python is the lingua franca of the self-hosted
  ecosystem we recruit from.
- **−** Must enforce streaming discipline (BC-6) — the framework permits bad
  patterns; tests gate it.
- **−** In-process rate limiting is only exact because we run one process; documented
  caveat if someone scales workers.
