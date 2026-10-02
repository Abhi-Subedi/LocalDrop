# LocalDrop Documentation

Two kinds of document live here: **user guides** you need to run the thing, and
the **engineering record** — the specification and decision history that explain
why it works the way it does.

## User guides

Start with the one that matches what you want to do.

| Guide | Read it when |
|---|---|
| [INSTALLATION.md](INSTALLATION.md) | Installing on any platform, first-run setup, reverse proxies, upgrading, troubleshooting |
| [DEMO.md](DEMO.md) | The public demo: running one, and what demo mode does |
| [CONFIGURATION.md](CONFIGURATION.md) | You need to change a setting. Every `LOCALDROP_*` variable, with defaults |
| [BACKUP.md](BACKUP.md) | Backing up, restoring, or rehearsing a restore |
| [SECURITY.md](SECURITY.md) | Threat model, what is already defended, how to harden a deployment |
| [API.md](API.md) | You are writing a client |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Building from source, running tests, cutting a release |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | You want to contribute code |
| [SECURITY.md](../SECURITY.md) (root) | Reporting a vulnerability — privately |
| [SUPPORT.md](../SUPPORT.md) | Where to ask for help |

## Engineering record

Written before implementation and kept as the record of why. Read
`spec/` in order for the full picture.

```text
docs/
├── INSTALLATION.md  CONFIGURATION.md  BACKUP.md
├── SECURITY.md  API.md  DEVELOPMENT.md  DEMO.md
├── spec/
│   ├── 01-product-vision.md           Product vision, problem, users, use cases, principles
│   ├── 02-requirements.md             Functional + non-functional requirements, roadmap
│   ├── 03-architecture.md             System architecture & technology evaluation
│   ├── 04-database.md                 Database schema, migrations, invariants
│   ├── 05-api.md                      REST API v1 + realtime events
│   ├── 06-security-privacy.md         Threat model, authn/authz, privacy model
│   ├── 07-frontend-design.md          Pages, design system, accessibility, i18n
│   ├── 08-engineering.md              Repo structure, dev env, testing, CI/CD, releases
│   ├── 09-diagrams.md                 Mermaid diagrams (system, flows, ERD, deployment)
│   ├── 10-risks-open-questions.md     Risks, open questions, decision log
│   └── 11-build-contract.md           ★ The Build Contract — binding decisions
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
    ├── ADR-010-license.md             AGPL-3.0-only [Accepted]
    └── ADR-011-packaging-distribution.md  ★ Native binaries, installers, GHCR
```

The execution roadmap is
[`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) (repo root).

## Status legend

Claims in the specification carry one of four markers. Anything unmarked is
**Proposed** by default.

| Marker | Meaning |
|---|---|
| *(unmarked)* | **Proposed** — designed, not validated by running code |
| `[NEEDS VALIDATION]` | An assumption that must be tested before relying on it |
| `[DECISION REQUIRED]` | Genuinely open; the maintainer must ratify it |
| `[FUTURE]` | Deliberately deferred; do not build in the current phase |

## Decision state (2026-10-01)

- **Accepted:** all eleven ADRs. AGPL-3.0-only licensing (ADR-010) and the
  packaging and distribution model (ADR-011) were both ratified for 1.1.0.
- **Implemented and tested:** the V1 architecture in `03-architecture.md` and the
  Build Contract. `1.0.0` shipped the server; `1.1.0` added every install path.
- **Open:** Phase-2+ questions in `10-risks-open-questions.md` — the email/SMTP
  role, locale choices, and mDNS feasibility, which remains
  `[NEEDS VALIDATION]`. Note that `LOCALDROP_MDNS_ENABLED` is a reserved
  setting and is not used yet.
- **Future:** the CLI client (spec 08 §11), S3/MinIO backends, multi-volume
  storage, OAuth, multi-user accounts.

### Known gaps, tracked rather than assumed

`scripts/check_fr_traceability.py` maps every Must-have requirement to the tests
that cover it. Nine are registered in its `KNOWN_GAPS` register with a reason —
not implemented, client-side only, or a documentation deliverable. The check
fails on any *new* uncovered requirement and on a `KNOWN_GAPS` entry that has
gone stale, so the set can only shrink. Run
`python scripts/check_fr_traceability.py` to see the current map.
