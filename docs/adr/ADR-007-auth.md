# ADR-007 — Authentication & authorization: DB sessions, cookies, argon2id, RBAC

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

Two client classes: browsers (ambient credential, CSRF-relevant) and API/CLI
(explicit credential). Self-hosted single-server reality: sessions can be checked in
the DB on every request (no stateless-token scale pressure). v1 has one owner;
Phase 2 adds users and per-folder ACLs — the model must extend without rework.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **Opaque DB sessions in cookies + PATs** | Instantly revocable; auditable ("which devices?"); no token crypto to get wrong; CSRF addressable by SameSite + custom header | DB lookup per request (cheap; indexed); cookie auth needs CSRF care |
| B | **JWT (access + refresh)** | Stateless verification; standard for multi-service | Revocation requires a denylist = state anyway; refresh-token rotation is a bug farm; strictly worse for single-server |
| C | **Server-side sessions + JWT for API** | Hybrid | Two auth systems, two threat models, one small team |

## Decision

**Option A.**

- **Passwords:** argon2id (memory 64 MiB, t=3, p=4; re-benchmarked at release — V4).
- **Sessions:** 256-bit opaque token; cookie `ld_session` (HttpOnly, SameSite=Lax,
  Secure-on-TLS); DB stores sha256(token); idle 7 d + absolute 30 d; rotation on
  login; revocation on password change.
- **CSRF:** unsafe methods under cookie auth require `X-Requested-With: localdrop`
  (non-simple header ⇒ cross-origin attackers hit CORS preflight, which never passes).
- **PATs:** 40-char random, sha256-at-rest, scopes `read|write|metrics`, last-used
  tracking; Bearer header; CSRF-exempt (no ambient credential).
- **AuthZ:** role enum `owner/admin/user/viewer` in schema from day one; **all checks
  are object-level in services** via owned-fetch helpers (BC-10) so Phase 2 folder
  ACLs swap the helper's internals, not the call sites.
- **Onboarding:** one-time console-printed setup token creates the owner (06 §3).

## Consequences

- **+** "Log out everywhere" and the session-list UI are trivial and real.
- **+** AuthZ evolution (Phase 2) is additive by construction.
- **−** Every request costs one indexed DB hit — measured, acceptable, cacheable
  per-request; revisit only with evidence.
