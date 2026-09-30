# ADR-003 — No Redis / no broker in v1

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

Redis-class infrastructure typically appears for: rate limiting, background-job
queues, and pub/sub fan-out (SSE). The question is whether LocalDrop v1 needs any of
them given its one-process shape (ADR-001).

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **Add Redis** | Shared rate-limit state; robust queue semantics; pub/sub for multi-process | Third container; new failure mode; +RAM cost on Pi-class hosts; none of its powers are needed while single-process |
| B | **No external infra: in-process rate limiter, in-process asyncio job scheduler, in-process EventBus** | Zero extra ops; fits the "five minutes to first file" principle (P4); perfectly accurate *because* single-process | Becomes wrong the moment we scale processes; limited job persistence (job state in Postgres mitigates) |
| C | **Postgres-backed queue (e.g. procrastinate/SKIP LOCKED)** | Durable jobs without Redis | Adds a framework for a job volume that is ~units/minute; premature |

## Decision

**Option B.** Jobs are DB-tracked rows with an in-process tick-loop scheduler
(03 §3.3); rate limiting is in-process token-bucket per class; SSE fan-out is a
bounded in-memory EventBus. **Revisit triggers (explicit):** ≥ 2 app replicas, job
backlog persistently exceeding scheduler capacity, or SSE fan-out lag — any one of
them reopens this ADR (likely landing on Postgres-backed queues first, Redis last).

## Consequences

- **+** Raspberry-Pi-friendly memory footprint; simplest possible failure surface.
- **−** Restarting the process pauses jobs mid-flight (they resume; jobs are
  idempotent by design).
- **−** If someone deploys multi-worker against docs, rate limits become per-worker —
  documented prominently, and the docs recommend the supported single-process shape.
