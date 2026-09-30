# 04 — Database Architecture

*Status: Proposed. PostgreSQL 16, SQLAlchemy 2.0 typed models, Alembic migrations.
The DDL sketches below are specification-grade (types, constraints, indexes) — final
DDL lives in code and migrations.*

---

## 1. Design rules

1. **UUIDs (`uuid v7`-style, time-ordered) as primary keys** everywhere except
   link/junction tables — unguessable in URLs, index-friendly.
2. **Timestamps are `timestamptz`, UTC always** (`created_at` on every table,
   `updated_at` where mutable).
3. **Soft deletion only where users can undo:** `files` and `folders` (trash).
   Shares are revoked, not deleted. Sessions/tokens hard-delete. Blobs are never
   soft-deleted — they're GC'd when unreferenced.
4. **Names are stored normalized NFC, ≤ 255 bytes**, with uniqueness enforced
   *per parent* via a functional unique index on `lower(name)`.
5. **All access control is in SQL-reachable columns** (owner/role/share rows) so
   authorization is testable with one query per rule — no logic that lives only in
   Python.
6. Migrations are **forward-only**; downgrade = restore backup (documented in
   08 §versioning).

---

## 2. Entity overview

```text
users ─┬─< sessions
       ├─< personal_access_tokens
       ├─< folders (owner)          folders ── self-ref parent
       ├─< files (uploader)         files >─── blobs (N files : 1 blob)
       ├─< upload_sessions
       ├─< shares (creator)
       └─< audit_events (actor)

shares ──< share_downloads          files/folders ──< shares (target)
```

---

## 3. Tables

### 3.1 `users`

| Column | Type | Constraints / notes |
|---|---|---|
| `id` | `uuid` | PK |
| `username` | `citext` | unique, 3–32 chars, `[a-z0-9_.-]` |
| `email` | `citext` | unique **nullable** (SMTP optional) |
| `password_hash` | `text` | argon2id encoded string |
| `role` | `text` | `check in ('owner','admin','user','viewer')` — v1 only `owner` rows exist; enum complete from day one |
| `is_active` | `boolean` | default `true`; soft-disable |
| `quota_bytes` | `bigint` | nullable = unlimited *(used Phase 2)* |
| `created_at` / `updated_at` | `timestamptz` | |

Indexes: `unique(username)`, `unique(email) where email is not null`.
*Phase 2 columns present now:* `email_verified_at timestamptz null`.

### 3.2 `sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK |
| `user_id` | `uuid` | FK → users **on delete cascade** |
| `token_hash` | `text` | **sha256 of the opaque cookie token** — raw token never stored |
| `created_at`, `last_seen_at`, `expires_at`, `absolute_expires_at` | `timestamptz` | idle + absolute limits (03 §9) |
| `ip` | `inet` | last-seen IP |
| `user_agent` | `text` | truncated 512 |
| `revoked_at` | `timestamptz` | nullable |

Indexes: `unique(token_hash)`, `index(user_id)`, `index(expires_at)` (GC scan).
Invariant: a session is valid iff `revoked_at is null and now() < least(expires_at,
absolute_expires_at) and user.is_active`.

### 3.3 `personal_access_tokens`

`id uuid PK`, `user_id FK cascade`, `name text` (user label, ≤ 100), `token_hash text
unique` (sha256; raw shown once), `scopes text[]` ⊆ `{read,write}`, `created_at`,
`last_used_at`, `expires_at nullable`, `revoked_at nullable`. Index `(user_id)`.

### 3.4 `folders` — the virtual tree

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK |
| `parent_id` | `uuid` | FK → folders **on delete cascade**; NULL = root (per-owner root implied, not a row) |
| `name` | `text` | 1–255 bytes, NFC, no `/`, no control chars |
| `owner_id` | `uuid` | FK → users *(denormalized from root ancestor for O(1) authz; Phase 2 sharing recomputes on move)* |
| `created_at`, `updated_at`, `deleted_at` | `timestamptz` | `deleted_at` null ⇒ live |

Constraints & indexes:
- `unique(parent_id, lower(name)) where deleted_at is null` — case-insensitive
  uniqueness among live siblings (partial index lets trash keep collisions).
- `index(owner_id)`, `index(parent_id)`.
- **No cycles possible:** edges only point parent→child at insert/move time
  (service validates `new_parent` is not self/descendant — enforced in service +
  integration test; a DB-level guard via recursive CTE trigger is [FUTURE] belt-and-braces).

### 3.5 `blobs` — content-addressed bytes

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK |
| `sha256` | `bytea` (32 B) | unique where status = verified |
| `size` | `bigint` | bytes; `check (size >= 0)` |
| `status` | `text` | `check in ('pending','verified')` — `pending` while hash job runs |
| `storage_path` | `text` | internal path under data dir |
| `mime_hint` | `text` | from upload, informational only |
| `created_at` | `timestamptz` |

Indexes: `unique(sha256) where status='verified'` (dedup lookup), `index(status)`
(job queue), `index(created_at)` (GC).
Invariant: a `verified` blob's `storage_path` **must** equal the derivable path from
`sha256` (03 §4.1) — checked by the integrity job.

### 3.6 `files`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK |
| `folder_id` | `uuid` | FK → folders on delete cascade (folder delete ⇒ files to trash? **No:** cascade hard-deletes; folder-delete is itself a soft-delete that cascades as soft — see §5 invariants) |
| `name` | `text` | 1–255 bytes NFC (same rules as folders) |
| `blob_id` | `uuid` | FK → blobs **restrict** (never orphan a blob reference) |
| `mime_type` | `text` | stored type; serving policy keyed off this + magic-byte re-check (06 §4) |
| `size` | `bigint` | denormalized from blob (display & sort without join) |
| `uploader_id` | `uuid` | FK → users |
| `created_at`, `updated_at`, `deleted_at` | `timestamptz` | trash |

Indexes: `unique(folder_id, lower(name)) where deleted_at is null`; `index(uploader_id)`;
`index(blob_id)`; `pg_trgm` GIN index on `name` for search: `gin (name gin_trgm_ops)`.

### 3.7 `upload_sessions`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK (tus upload id) |
| `user_id` | `uuid` | FK cascade |
| `folder_id` | `uuid` | FK restrict — target must exist |
| `file_name` / `mime_type` | `text` | validated like `files.name` |
| `total_size` | `bigint` | declared at creation; `check (total_size >= 0)` |
| `offset` | `bigint` | `check (0 <= offset <= total_size)` |
| `status` | `text` | `check in ('active','finalized','cancelled','expired')` |
| `chunk_hashes` | `jsonb` | array of `{offset, sha256}` for resume-time chunk revalidation `[NEEDS VALIDATION: size for 100k-chunk uploads — cap history, re-read-tail fallback]` |
| `staging_path` | `text` | internal |
| `created_at`, `expires_at` | `timestamptz` | TTL 7 d default |

Indexes: `index(user_id, status)`, `index(expires_at)`.

### 3.8 `shares`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK (internal) |
| `token` | `text` | **26-char base32 (130 bits)** of CSPRNG output — the URL secret; unique |
| `target_type` | `text` | `check in ('file','folder')` *(v1: 'file'; folder Phase 2)* |
| `file_id` / `folder_id` | `uuid` | FK restrict; exactly one non-null (`check` constraint) |
| `created_by` | `uuid` | FK → users |
| `expires_at` | `timestamptz` | nullable = never |
| `max_downloads` | `integer` | nullable = unlimited |
| `download_count` | `integer` | default 0 — maintained from `share_downloads` |
| `password_hash` | `text` | nullable (argon2id) |
| `revoked_at` | `timestamptz` | nullable |
| `created_at` | `timestamptz` | |

Indexes: `unique(token)`, `index(created_by)`, `index(expires_at)`.
Invariant: valid ⇔ `revoked_at is null and (expires_at is null or now() < expires_at)
and (max_downloads is null or download_count < max_downloads)`.

### 3.9 `share_downloads`

`id bigserial PK`, `share_id FK cascade`, `session_key text` (random cookie issued per
share-password unlock / first hit — counts humans not segments), `file_id FK`,
`ip inet`, `user_agent text`, `created_at`.
Index `(share_id, session_key)` unique — one counting row per human per share;
`(share_id, created_at)` for time-bounded abuse checks.

### 3.10 `audit_events`

`id uuid PK`, `actor_id uuid null` (null = system/anonymous), `actor_ip inet null`,
`action text` (namespaced: `auth.login`, `auth.login_failed`, `file.delete`,
`share.create`, `share.access_granted`, `share.password_failed`, `upload.finalize`,
`settings.change`, …), `target_type text null`, `target_id uuid null`,
`details jsonb default '{}'`, `created_at timestamptz`.
Indexes: `(actor_id, created_at desc)`, `(action, created_at desc)`, BRIN on
`created_at` (append-only table); partitioning by month is [FUTURE] (volumes don't
justify it).

### 3.11 `settings`

`key text PK`, `value jsonb`, `updated_at`. Runtime-mutable instance settings
(Phase 4 UI); v1 uses it only for onboarding-completed marker and schema-level
feature flags.

---

## 4. Cleanup jobs → tables (mapping)

| Job (03 §3.3) | Tables touched |
|---|---|
| `upload_gc` | delete `upload_sessions` (expired/cancelled) + staging files |
| `trash_gc` | hard-delete `files`/`folders` rows past retention → deref blobs |
| `blob_gc` (same job, second step) | delete `blobs` with zero live-or-trashed `files` refs **and** status verified, then unlink file |
| `share_gc` | flag expired; count-limit is enforced at read time (no write needed) |
| `session_gc` | delete sessions past `least(expires_at, absolute_expires_at)` |

---

## 5. Key invariants (test-enforced)

1. Two live siblings never share `lower(name)` (files & folders independently).
2. A `files` row always points at an existing `blobs` row (`restrict` FK + finalize
   ordering from 03 §5.5).
3. `files.size == blobs.size` for the referenced blob (trigger-enforced update).
4. Folder graph is acyclic (service validation + integration test).
5. `blobs` storage paths match `sha256` derivation for `verified` rows.
6. Sum of live `files.size` per user ≤ `quota_bytes` when set (Phase 2; enforced in
   upload service with a re-check inside the creation transaction).
7. `download_count` = count of `share_downloads` rows (nightly reconciliation job
   logs drift).

---

## 6. Migrations & versioning

- **Alembic**, one migration per PR touching models; migration files reviewed as code.
- **Auto-upgrade on container start:** entrypoint runs `alembic upgrade head` before
   serving; refuses to start if the DB schema is *newer* than the app supports
   (downgrade = restore, documented).
- **Pre-upgrade safety valve:** if `LOCALDROP_BACKUP_BEFORE_MIGRATE=true` (compose
  default on), entrypoint runs `pg_dump` to the data dir before migrating. This is a
  convenience, not a substitute for real backups (docs say so loudly).
- Seed/dev data via `scripts/seed.py` (dev only — never in the production image).

---

*Next: [05 — API](05-api.md). ER diagram: [09-diagrams §7](09-diagrams.md).*
