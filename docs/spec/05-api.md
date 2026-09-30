# 05 — API Architecture (REST v1)

*Status: Proposed. OpenAPI 3.1 is generated from FastAPI/Pydantic models — the
running `/docs` and the published spec are the same artifact (principle P8).*

---

## 1. Conventions

- Base path `/api/v1`. JSON everywhere except the two byte endpoints (upload PATCH,
  download GET) and SSE.
- **Auth:** session cookie (`ld_session`; HttpOnly, `SameSite=Lax`, `Secure` when the
  request is HTTPS) **or** `Authorization: Bearer <PAT>`. Public share endpoints use
  a separate short-lived `ld_share` cookie after link/password unlock.
- **CSRF:** unsafe methods (POST/PATCH/PUT/DELETE) with cookie auth require the
  `X-Requested-With: localdrop` header (custom-header defense — cannot be sent
  cross-origin by forms; simpler than double-submit and equivalent strength here).
  Bearer-auth requests are CSRF-exempt (no ambient credentials).
- **Errors:** RFC 9457 problem+json —

  ```json
  { "type": "https://localdrop.dev/errors/offset-conflict",
    "title": "Upload offset conflict",
    "status": 409, "detail": "Expected offset 52428800, got 50000000.",
    "request_id": "req_…" }
  ```

- **Pagination:** cursor-based (`?limit=50&cursor=…`, ordered lists return
  `next_cursor`). Listing endpoints never offset-paginate (tree data + concurrent
  mutation makes offsets lie).
- **Rate limits** in responses: `RateLimit-Limit` / `RateLimit-Remaining` /
  `RateLimit-Reset` (draft IETF headers); `429` with `Retry-After`.

### 1.1 Rate limit classes (defaults, all configurable)

| Class | Scope | Limit |
|---|---|---|
| `auth` | login, password change, share unlock | 10 / 5 min / (IP + target identity) |
| `share` | public share endpoints | 120 / min / IP |
| `content` | download content | 30 / min / user or share session |
| `api` | everything else authenticated | 600 / min / user |
| `upload` | PATCH chunks | exempt from `api` (chunk traffic is legit bulk); bounded by session cap instead |

---

## 2. Endpoints

Legend: Auth = `S` session, `P` PAT, `—` public (share context). All authenticated
endpoints also accept PAT unless marked `S only`.

### 2.1 System

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/v1/health/live` | — | Process is up (no DB touch) |
| `GET /api/v1/health/ready` | — | DB reachable + storage writable + migrations current |
| `GET /metrics` | P (`metrics` scope) `[admin-only]` | Prometheus exposition |

### 2.2 Setup & auth

| Method & path | Auth | Purpose / notes |
|---|---|---|
| `GET /api/v1/setup/status` | — | `{onboarding_required: bool}` — true until owner exists |
| `POST /api/v1/setup/owner` | setup token | Create owner (username, password). Token from console. 410 after use. |
| `POST /api/v1/auth/login` | — | username+password → session cookie. `401` problem; audit `auth.login(_failed)`; lockout backoff per rate class `auth`. |
| `POST /api/v1/auth/logout` | S | Revoke current session. |
| `GET /api/v1/auth/sessions` | S | List own sessions (device, ip, last_seen). |
| `DELETE /api/v1/auth/sessions/{id}` | S | Revoke one (not current unless `?everywhere`). |
| `GET /api/v1/me` | S/P | Profile + storage usage summary. |
| `PATCH /api/v1/me` | S/P | Change display name. |
| `PUT /api/v1/me/password` | S | `{current, new}` → revoke all other sessions. |
| `GET/POST/DELETE /api/v1/me/tokens[/{id}]` | S | PAT CRUD; create returns raw token **once**. |

### 2.3 Folders

| Method & path | Purpose | Errors beyond 4xx-standard |
|---|---|---|
| `GET /api/v1/folders/{id}/children` | List children (files+folders mixed, `?type=`, `?sort=name|size|created_at`, `?q=` search within subtree via pg_trgm; cursor-paged) | `404` |
| `POST /api/v1/folders` | Create (`{parent_id|null, name}`) | `409` name collision |
| `PATCH /api/v1/folders/{id}` | Rename (`{name}`) | `409` collision |
| `POST /api/v1/folders/{id}/move` | `{new_parent_id}` | `409` collision, `422` cycle/into-self |
| `DELETE /api/v1/folders/{id}` | Soft-delete subtree → trash | — |
| `POST /api/v1/folders/{id}/restore` | From trash | `409` collision at destination |
| `GET /api/v1/folders/{id}/path` | Breadcrumb chain | — |

*(All v1 routes are owner-only; the permission dependency exists from day one and
v1 simply has one owner — Phase 2 swaps the check, not the routes.)*

### 2.4 Files

| Method & path | Purpose |
|---|---|
| `GET /api/v1/files/{id}` | Metadata (incl. `hash_status`) |
| `PATCH /api/v1/files/{id}` | Rename |
| `POST /api/v1/files/{id}/move` | `{folder_id}` (collision → `409` with `?overwrite=true` option) |
| `POST /api/v1/files/{id}/copy` | Same-folder copy or cross-folder (`{folder_id}`); references same blob (instant, no bytes) |
| `DELETE /api/v1/files/{id}` | Soft-delete → trash |
| `POST /api/v1/files/{id}/restore` | — |
| `GET /api/v1/files/{id}/thumbnail?size=256|1024` | WebP (404 until generated; client retries on SSE `job.progress`) |
| `GET /api/v1/files/{id}/preview` | Text preview (≤ 256 KiB, `{text, charset, truncated}`) — PDF/AV use `content` with inline disposition |
| `GET /api/v1/files/{id}/content` | **Download** — streaming, Range/ETag per 03 §6 |
| `GET /api/v1/trash` / `POST /api/v1/trash/purge` | List / empty trash |

### 2.5 Uploads (tus subset — see 03 §5.1)

| Method & path | Purpose |
|---|---|
| `POST /api/v1/uploads` | Create session `{fileName, folderId, totalSize, mimeType?}` → `201` + `Location` |
| `HEAD /api/v1/uploads/{id}` | `Upload-Offset`, `Upload-Expires` |
| `PATCH /api/v1/uploads/{id}` | Append chunk (octet-stream, offset header, optional `Upload-Checksum: sha256 …`) |
| `DELETE /api/v1/uploads/{id}` | Cancel + cleanup |
| `GET /api/v1/uploads` | Own sessions (for UI resume-after-reload) |

Errors: `460` (offset/checksum conflict, tus-style), `413` (total size over max),
`423` when storage free space < 102 % of need, `404` expired/unknown (expired
sessions look identical to unknown — no enumeration).

### 2.6 Shares

| Method & path | Purpose |
|---|---|
| `POST /api/v1/shares` | Create: `{targetType:'file'|'folder', targetId, expiresAt?, maxDownloads?, password?}` → `{token, url, qrSvg}` (QR generated **in-process**, no external API) |
| `GET /api/v1/shares` | Own shares + live counters |
| `PATCH /api/v1/shares/{id}` | Update expiry/limit/password (change = new audit event) |
| `DELETE /api/v1/shares/{id}` | Revoke |
| **Public surface** (rate class `share`): | |
| `GET /api/v1/shares/{token}` | Share metadata (filename, size, requiresPassword, locked state — **no file content**) |
| `POST /api/v1/shares/{token}/unlock` | Password → `ld_share` cookie (HttpOnly, scoped path, 1 h) |
| `GET /api/v1/shares/{token}/files/{fileId}/content` | Stream (folder listing: Phase 2) |

### 2.7 Realtime

| Method & path | Purpose |
|---|---|
| `GET /api/v1/events` | SSE stream (S only — 403 for PAT; envelope per 03 §8) |

### 2.8 Admin *(v1: minimal — Phase 2 grows it)*

| Method & path | Purpose |
|---|---|
| `GET /api/v1/admin/stats` | Storage usage, session count, upload sessions, share counts |
| `GET /api/v1/admin/audit?cursor=…` | Audit feed |

---

## 3. Standard error catalog

| Status | `type` suffix | When |
|---|---|---|
| 400 | `validation` | Pydantic reject |
| 401 | `unauthenticated` / `bad-credentials` | no/invalid principal |
| 403 | `forbidden` / `csrf` / `share-locked` / `share-expired` / `share-limit-reached` | authorization failures (share states use 403, not 404, only **after** token validity is proven; unknown tokens → 404) |
| 404 | `not-found` | unknown id — identical body for "not yours" |
| 409 | `name-collision` / `offset-conflict` | sibling name / tus offset |
| 413 | `too-large` | over max upload |
| 422 | `cycle` / `unprocessable` | move-into-descendant etc. |
| 423 | `storage-full` | free-space check |
| 429 | `rate-limited` | with `Retry-After` |
| 460 | `checksum-mismatch` | tus chunk checksum (tus reserves 460 for conflicts) |
| 500 | `internal` | request_id echoed; no internals leaked |

---

## 4. API stability & versioning

- `/api/v1` contract is additive within a major: new optional fields yes, removals/
  renames no. Breaking ⇒ `/api/v2` + ≥ 6-month overlap.
- OpenAPI spec is CI-frozen: a generated diff against `docs/openapi-v1.json` fails the
  build on undocumented change (no silent contract drift).
- Deprecation: `Deprecation` + `Sunset` headers, one minor version minimum notice
  (NFR-15).

---

## 5. WebSocket? — answered

Considered and declined for v1 *(ADR-006)*: no client→server streaming need exists;
SSE covers server→client; SSE survives reverse proxies that misroute WebSocket
upgrades — a real-world self-hosting pain we sidestep entirely. Revisit trigger:
collaborative or device-sync features requiring bidirectional push.

---

*Next: [06 — Security & privacy](06-security-privacy.md).*
