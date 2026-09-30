# LocalDrop Documentation

This directory contains the **LocalDrop Master Specification** — the complete product
and technical design produced *before* implementation (Phase 0). The execution
roadmap that turns this specification into phased, tracked work is
[`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) (repo root).

## How to review

Read in order for the full picture, or jump to what you care about:

```text
docs/
├── README.md                          ← you are here (index + status legend)
├── spec/
│   ├── 01-product-vision.md           Product vision, problem, users, use cases, principles
│   ├── 02-requirements.md             Functional + non-functional requirements, roadmap, MVP
│   ├── 03-architecture.md             System architecture & technology evaluation
│   ├── 04-database.md                 Database schema, migrations, invariants
│   ├── 05-api.md                      REST API v1 + realtime events
│   ├── 06-security-privacy.md         Threat model, authn/authz, privacy model
│   ├── 07-frontend-design.md          Pages, design system, accessibility, i18n
│   ├── 08-engineering.md              Repo structure, dev env, config, testing, CI/CD, Docker
│   ├── 09-diagrams.md                 Mermaid diagrams (system, flows, ERD, deployment)
│   ├── 10-risks-open-questions.md     Risks, open questions, decision log
│   └── 11-build-contract.md           ★ The Build Contract — binding decisions for implementation
└── adr/
    ├── ADR-001-backend-framework.md   FastAPI over Node/Go
    ├── ADR-002-database.md            PostgreSQL; no Redis; SQLite deferred
    ├── ADR-003-no-redis.md            In-process jobs, rate limits, pub/sub-free v1
    ├── ADR-004-storage.md             Content-addressed local filesystem blob store
    ├── ADR-005-upload-protocol.md     tus 1.0.0 subset for resumable uploads
    ├── ADR-006-realtime.md            Server-Sent Events over WebSocket
    ├── ADR-007-auth.md                DB sessions + cookies + argon2id + RBAC
    ├── ADR-008-frontend.md            React + Vite SPA, TanStack, Tailwind
    ├── ADR-009-deployment.md          Two-container Docker Compose
    └── ADR-010-license.md             AGPL-3.0 recommendation [DECISION REQUIRED]
```

## Status legend

Every significant claim in this specification carries one of four statuses. Anything
unmarked is **Proposed** (the default for architecture that has not been built yet).

| Marker | Meaning |
|---|---|
| *(unmarked)* | **Proposed** — designed, not yet validated by running code |
| `[NEEDS VALIDATION]` | Assumption that must be tested empirically before relying on it |
| `[DECISION REQUIRED]` | Genuinely open; the maintainer must ratify before implementation |
| `[FUTURE]` | Deliberately deferred; do **not** build in the current phase |

## Current decision state (2026-10-01)

- **Confirmed:** all ten ADRs, including **AGPL-3.0 licensing** (ADR-010 ratified
  2026-10-01; `LICENSE` added to the repo root).
- **Proposed:** the full architecture in `03-architecture.md` and the Build Contract.
- **Open:** remaining items in `10-risks-open-questions.md` (Phase-2+ questions such
  as the email/SMTP role and locale choices; mDNS feasibility remains
  `[NEEDS VALIDATION]`).
- **Future:** CLI, plugin system, S3/MinIO backend, multi-volume storage, OAuth.

Implementation must not begin until this specification is reviewed and approved
(see `11-build-contract.md`). The execution roadmap is
[`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md).
