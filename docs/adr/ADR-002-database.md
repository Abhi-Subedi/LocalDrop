# ADR-002 — Database: PostgreSQL

**Status:** Proposed (blocks Phase 1). **Date:** 2026-09-30.

## Context

LocalDrop's data is deeply relational (folder tree with uniqueness constraints,
shares referencing targets, sessions/users/audit). It also needs name search over
large listings and clean concurrent write behavior (uploads commit offsets; audit
appends). Deployment target includes Docker, where a second container is cheap.

## Options

| | Option | Strengths | Weaknesses |
|---|---|---|---|
| A | **PostgreSQL 16** | Real constraints & partial/functional unique indexes (case-insensitive sibling names), `pg_trgm` search, JSONB, mature backup/restore, great ORM/migration story | Second container; ~30 MB RAM floor (fine everywhere we target) |
| B | **SQLite** | Zero ops; perfect single-user fit; file-copy backup | Concurrent-write contention with audit/offset churn; weaker tooling under load; two databases to support if we also want Postgres |
| C | **MariaDB/MySQL** | Familiar to some admins | No advantage here; worse partial-index story |
| D | **MongoDB** | — | Wrong model: tree + shares + constraints is relational |

## Decision

**PostgreSQL 16** via SQLAlchemy 2.0 (typed) + Alembic. **SQLite is [FUTURE]** as a
"single-binary lite mode" — the ORM keeps it reachable, but v1 tests against
Postgres only; supporting both in v1 doubles the test matrix for zero MVP users.

## Consequences

- **+** Sibling-name uniqueness (files & folders) is a partial functional index, not
  application hope; search is a GIN trigram index, not a scan.
- **+** `pg_dump` + data dir = complete, documented, CI-drilled backup story.
- **−** Compose stack has two containers (accepted; ADR-009 shapes it).
- **−** Team must write migrations for every change — that friction is a feature.
