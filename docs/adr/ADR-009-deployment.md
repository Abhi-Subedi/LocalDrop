# ADR-009 — Deployment: two-container Docker Compose, no proxy container

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

The flagship deployment is a home server/Pi/NAS: `docker compose up` → working
LocalDrop on the LAN. TLS and remote access are the deployer's perimeter (Caddy/
Traefik/nginx/tailscale already in place in homelabs); mandating our own proxy
container duplicates their choice. mDNS discovery interacts with Docker networking
and must be handled honestly (03 §7).

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **App + Postgres, no proxy** | Minimal footprint; deployer keeps their perimeter; app serves SPA + streams fine itself | We must document TLS snippets per proxy (done — 08 §7); no baked-in HTTPS |
| B | **Add Caddy/Traefik container (auto-HTTPS)** | One-stop HTTPS for remote exposure | Wrong default for LAN-first (self-signed noise on LAN, port-80 games); double proxying for homelab users; +1 container always |
| C | **All-in-one (embedded Postgres)** | Single container | DB-in-container upgrade/backup horror stories; fights ADR-002's ops story |
| D | **Kubernetes/Helm** | — | Absurd for the persona; rejected without ceremony |

## Decision

**Option A.** Compose stack: `localdrop` (image `ghcr.io/localdrop/localdrop`,
uid 1000, read-only rootfs, caps dropped, `/data` volume, `:8080` published,
healthcheck `/health/ready`) + `postgres:16` (internal network only, random
generated password, `pgdata` volume, `pg_isready` healthcheck). Entrypoint:
pre-flight checks → Alembic migrate (with `pg_dump` safety valve, 04 §6) → serve.
TLS/remote-access = documented snippets for the four common proxies + tailscale;
SSE/streaming-critical settings included (R8).

**mDNS posture (03 §7):** opt-in `network_mode: host` profile (Linux) enables
advertisement via python-zeroconf `[NEEDS VALIDATION: V2]`; default bridge mode
prints QR + LAN URLs and claims nothing it can't do. A Caddy-included *example*
compose variant is [FUTURE] for internet-first users.

## Consequences

- **+** Two containers, one volume, five minutes — on a Pi.
- **+** No port-80/domain requirements that break isolated-LAN installs.
- **−** Internet-first users read one docs page before exposing (acceptable; they'd
  customize a proxy anyway).
- **−** mDNS flagship experience is platform-honest rather than magical — QR carries
  the experience on Android (documented matrix).
