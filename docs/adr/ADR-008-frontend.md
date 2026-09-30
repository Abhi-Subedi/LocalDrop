# ADR-008 — Frontend: React + Vite SPA (not Next.js), TanStack, Tailwind, Radix

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

The UI is an authenticated, local-network tool: no SEO, no public marketing pages,
no SSR data benefit — but heavy client state (upload manager with resume, virtualized
10⁵-row file lists, drag-drop, offline-ish resilience). Deployment must be one
container serving everything (P4), with zero third-party runtime asset calls (BC-9).

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **Vite SPA (React 18 + TS)** | Static build the backend serves; tiny deploy; maximal ecosystem for virtualization/dnd/i18n; HMR speed | No SSR (not needed); client bundle discipline required (budget in 07 §6) |
| B | **Next.js** | SSR/ISR/routing; React Server Components | Solves problems we don't have; drags a Node runtime into production deployment; heavier image; overkill tax paid daily |
| C | **HTMX + server templates** | Minimal JS; one language | Upload manager, virtualized lists, and drag-drop want real client state; we'd hand-roll what React ecosystem gives free |

Within A: **TanStack Router** (type-safe routes, search-param state — the file
browser's filters/sort live in the URL) and **TanStack Query** (server cache with
SSE-driven invalidation, 03 §8). **Tailwind + Radix primitives** per the design
system (07 §3): Radix buys focus traps, roving tabindex, and ARIA wiring —
accessibility (P11/NFR-8) as library engineering, not heroics.

## Decision

**Option A** with the stack above. The built SPA is served by FastAPI from a
fingerprinted static dir; `index.html` is a non-cacheable fallback for client
routing; `/api/*` and `/` never collide, keeping reverse-proxy splits trivial.

## Consequences

- **+** One container serves the whole product (ADR-009 becomes clean).
- **+** Route-typed navigation catches link/refactor bugs at compile time.
- **−** Initial-bundle discipline is a standing obligation (budget + CI gate).
- **−** If docs/marketing pages arrive later, they should be static files or a
  separate site — not a reason to migrate the app to Next.js.
