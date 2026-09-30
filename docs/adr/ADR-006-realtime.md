# ADR-006 — Realtime: Server-Sent Events, not WebSocket

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

The UI needs server→client notifications (file list changes from other sessions,
share counters, job progress). There is no client→server streaming requirement: the
upload data path is HTTP PATCH by design (ADR-005), and everything else is normal
requests.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **WebSocket** | Bidirectional; binary frames | Bidirectionality unused; upgrade/`Upgrade` handling is the classic reverse-proxy misconfig in self-hosted deployments; heavier client impl; reconnect logic manual |
| B | **SSE** (`EventSource`) | One-way = exactly the need; plain HTTP; native auto-reconnect + `Last-Event-ID`; proxies treat it as a long GET (just disable buffering) | Text-only, one-way, ~6-connection-per-domain browser limit (irrelevant: one stream per tab) |
| C | **Polling only** | Zero infrastructure | Latency + chatter; feels dead vs. LAN-speed expectations |

## Decision

**SSE at `/api/v1/events`** — session-authenticated only (PATs rejected: tokens are
not ambient browser credentials), heartbeat every 20 s, bounded per-subscriber
queues with drop-oldest (a dropped event degrades to a client refetch, never
corruption). Envelope and event types per 03 §8. Every SSE consumer in the UI has a
30 s polling fallback — **no correctness may depend on the stream** (BC-8).

## Consequences

- **+** Deployment story stays proxy-simple — the #1 self-hosting support class
  (WebSocket-through-nginx) simply doesn't exist for us.
- **+** Reconnection semantics come free from the platform.
- **−** If a future feature needs client→server streaming (device sync, collaborative
  presence), this ADR reopens — WebSocket then, on a *separate* endpoint, SSE intact.
