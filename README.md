# LocalDrop

**Self-hosted, local-network-first file sharing. Fast, private, and yours.**

> ⚠️ **Status: Phase 0 — Specification.** LocalDrop is currently a documentation-first
> project. No implementation code exists yet. The architecture, database, API, security
> model, and roadmap below have been specified before building, on purpose.
> See [docs/README.md](docs/README.md) to review the full Master Specification.

## What LocalDrop is

LocalDrop is an open-source, self-hosted file-sharing platform designed primarily for
fast and private file transfer over a local network, with optional remote access.

- **Local-network-first** — install it on a home server, NAS, Raspberry Pi, or VPS and
  reach it instantly from any device on your Wi-Fi (QR-code onboarding, `.local`
  hostname, IP fallback).
- **Privacy-first** — zero telemetry, works fully offline, your server holds your data.
- **Handles real files** — resumable, chunked uploads and streaming, range-supported
  downloads for multi-gigabyte files without loading them into RAM.
- **Shareable** — public links with expiry, passwords, download limits, revocation,
  and QR codes.
- **Simple to run** — one `docker compose up`, one data volume, five minutes to your
  first transfer. No cloud account, no vendor lock-in.

## Documentation

| Document | Purpose |
|---|---|
| [Master Specification](docs/spec/01-product-vision.md) | Start here — product vision, users, principles |
| [Requirements & MVP](docs/spec/02-requirements.md) | Functional / non-functional requirements, roadmap, MVP definition |
| [Architecture](docs/spec/03-architecture.md) | System, storage, transfer, discovery, realtime architecture |
| [Database](docs/spec/04-database.md) | Schema, migrations, invariants |
| [API](docs/spec/05-api.md) | REST API v1 design |
| [Security & Privacy](docs/spec/06-security-privacy.md) | Threat model, auth, privacy model |
| [Frontend & Design](docs/spec/07-frontend-design.md) | Pages, design system, accessibility |
| [Engineering](docs/spec/08-engineering.md) | Repo layout, dev env, config, testing, CI/CD, Docker, releases |
| [Diagrams](docs/spec/09-diagrams.md) | Mermaid architecture and flow diagrams |
| [Risks & Open Questions](docs/spec/10-risks-open-questions.md) | What is unvalidated or undecided |
| [Build Contract](docs/spec/11-build-contract.md) | **The binding decisions future implementation must follow** |
| [Implementation Plan](IMPLEMENTATION_PLAN.md) | **Phase-by-phase execution roadmap (phases, slices, issues, milestones)** |
| [ADRs](docs/adr/ADR-001-backend-framework.md) | Architecture Decision Records |

## License

Recommended: **AGPL-3.0** (pending maintainer ratification — see
[ADR-010](docs/adr/ADR-010-license.md) for the tradeoff analysis).
